"""
Firebase Authentication integration with dev mode support.
"""
import os
from typing import Optional
from fastapi import Header, HTTPException
from firebase_admin import auth, credentials, initialize_app

# Firebase initialization flag
_firebase_initialized = False


def _is_dev_mode() -> bool:
    """Check if dev mode is enabled (dynamically)."""
    return os.getenv("DEV_MODE", "false").lower() == "true"


def init_firebase():
    """
    Initialize Firebase Admin SDK.

    Uses Application Default Credentials (same as Firestore).
    Call this once at app startup.
    """
    global _firebase_initialized

    if _firebase_initialized:
        return

    try:
        # Use Application Default Credentials (same as your Vision API & Firestore)
        cred = credentials.ApplicationDefault()
        initialize_app(cred)
        _firebase_initialized = True

        if _is_dev_mode():
            print("🔧 Firebase initialized (DEV MODE enabled)")
        else:
            print("🔒 Firebase initialized (Production mode)")

    except ValueError:
        # Already initialized
        _firebase_initialized = True
        print("✅ Firebase already initialized")
    except Exception as e:
        print(f"⚠️  Firebase initialization failed: {e}")
        if not _is_dev_mode():
            raise


async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_dev_user_id: Optional[str] = Header(None, alias="X-Dev-User-ID")
) -> str:
    """
    Extract and verify user_id from authentication.

    Production Mode (DEV_MODE=false):
        - Requires valid Firebase JWT token in Authorization header
        - Format: "Authorization: Bearer <token>"
        - Returns: user_id from verified token

    Development Mode (DEV_MODE=true):
        - Option 1: Pass X-Dev-User-ID header to impersonate any user
        - Option 2: No auth → defaults to "test_user_123"
        - Option 3: Valid Firebase token still works

    Args:
        authorization: Authorization header with Bearer token
        x_dev_user_id: Custom header for dev mode user override

    Returns:
        user_id (str): Verified user identifier

    Raises:
        HTTPException(401): If authentication fails

    Examples:
        # Production
        curl -H "Authorization: Bearer <firebase-token>" /trips

        # Development - impersonate user
        curl -H "X-Dev-User-ID: alice" /trips

        # Development - default user
        curl /trips
    """

    # ========================================
    # DEV MODE: Allow bypass for testing
    # ========================================
    if _is_dev_mode():
        # Option 1: Custom dev user
        if x_dev_user_id:
            print(f"⚠️  DEV MODE: Using X-Dev-User-ID={x_dev_user_id}")
            return x_dev_user_id

        # Option 2: No auth provided → default test user
        if not authorization:
            print("⚠️  DEV MODE: No auth provided, using test_user_123")
            return "test_user_123"

        # Option 3: Token provided → verify it (optional in dev mode)
        # This allows testing production-like auth in dev mode

    # ========================================
    # PRODUCTION: Verify Firebase token
    # ========================================
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header. Format: 'Authorization: Bearer <token>'"
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format. Expected: 'Bearer <token>'"
        )

    # Extract token
    token = authorization.split("Bearer ")[1].strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Empty token provided"
        )

    # Verify Firebase token
    try:
        decoded_token = auth.verify_id_token(token)
        user_id = decoded_token.get('uid')

        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Token does not contain user ID"
            )

        return user_id

    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token: Token is expired or malformed"
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    except auth.RevokedIdTokenError:
        raise HTTPException(
            status_code=401,
            detail="Token has been revoked"
        )
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}"
        )


def verify_internal_api_key(
    authorization: Optional[str] = Header(None),
) -> bool:
    """
    Verify that the request carries a valid internal API key.

    The key is set via INTERNAL_API_KEY env var and shared with
    trusted services (e.g. email parser).

    Returns True if valid, raises HTTPException(401) otherwise.
    """
    expected = os.getenv("INTERNAL_API_KEY")

    if _is_dev_mode() and not expected:
        # Dev mode without a key configured — allow through
        return True

    if not expected:
        raise HTTPException(status_code=401, detail="Internal API key not configured")

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization format. Expected: 'Bearer <key>'")

    token = authorization.split("Bearer ", 1)[1].strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid internal API key")

    return True


def resolve_user_by_email(email: str) -> str:
    """
    Look up a Firebase user's UID by their email address.

    Used by service-to-service endpoints where the calling service
    knows the user's email but not their Firebase UID.

    Args:
        email: The user's email address

    Returns:
        Firebase UID (str)

    Raises:
        HTTPException(404): If no user found for this email
        HTTPException(500): If Firebase lookup fails
    """
    if _is_dev_mode():
        # In dev mode, if Firebase isn't working, return a deterministic ID
        try:
            user_record = auth.get_user_by_email(email)
            return user_record.uid
        except Exception:
            # Fallback: use email as the user ID in dev mode
            print(f"⚠️  DEV MODE: Could not resolve email {email}, using email as user_id")
            return email

    try:
        user_record = auth.get_user_by_email(email)
        return user_record.uid
    except auth.UserNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"No user account found for email: {email}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resolve user by email: {str(e)}",
        )


def create_custom_token_for_testing(user_id: str = "test_user_123") -> str:
    """
    Create a Firebase custom token for testing.

    This is useful for generating test tokens without going through
    the full Firebase Authentication flow.

    Args:
        user_id: User ID to encode in the token

    Returns:
        Custom token (str) that can be exchanged for an ID token

    Usage:
        token = create_custom_token_for_testing("alice")
        # Use this token in Authorization: Bearer <token>
    """
    if not _firebase_initialized:
        init_firebase()

    custom_token = auth.create_custom_token(user_id)
    return custom_token.decode('utf-8')
