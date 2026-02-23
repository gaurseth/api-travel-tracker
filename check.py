#!/usr/bin/env python3
"""
Credential Checker for Travel Tracker API
Verifies Google Cloud and Firebase configuration
"""
import os
import sys
import json
from pathlib import Path

def print_header(text):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def print_success(text):
    """Print success message."""
    print(f"✅ {text}")

def print_error(text):
    """Print error message."""
    print(f"❌ {text}")

def print_info(text):
    """Print info message."""
    print(f"ℹ️  {text}")

def check_environment_variable():
    """Check if GOOGLE_APPLICATION_CREDENTIALS is set."""
    print_header("Step 1: Check Environment Variable")

    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if not creds_path:
        print_error("GOOGLE_APPLICATION_CREDENTIALS is not set!")
        print_info("To fix this, run:")
        print_info('  export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your-key.json"')
        print_info("\nOr add to ~/.zshrc or ~/.bashrc:")
        print_info('  echo \'export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your-key.json"\' >> ~/.zshrc')
        return None

    print_success(f"GOOGLE_APPLICATION_CREDENTIALS is set")
    print_info(f"Path: {creds_path}")
    return creds_path

def check_file_exists(creds_path):
    """Check if the credentials file exists."""
    print_header("Step 2: Check File Exists")

    if not Path(creds_path).exists():
        print_error(f"File does not exist: {creds_path}")
        print_info("Make sure you downloaded the service account key from:")
        print_info("  https://console.cloud.google.com/iam-admin/serviceaccounts")
        return False

    print_success("Credentials file exists")

    # Check if file is readable
    if not os.access(creds_path, os.R_OK):
        print_error("File exists but is not readable!")
        print_info("Fix permissions with:")
        print_info(f"  chmod 600 {creds_path}")
        return False

    print_success("File is readable")
    return True

def read_credentials(creds_path):
    """Read and parse the credentials file."""
    print_header("Step 3: Read Credentials")

    try:
        with open(creds_path, 'r') as f:
            creds = json.load(f)

        print_success("Credentials file is valid JSON")
        return creds
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON in credentials file: {e}")
        return None
    except Exception as e:
        print_error(f"Error reading credentials: {e}")
        return None

def display_project_info(creds):
    """Display project information from credentials."""
    print_header("Step 4: Project Information")

    required_fields = ["type", "project_id", "client_email", "private_key"]
    missing_fields = [field for field in required_fields if field not in creds]

    if missing_fields:
        print_error(f"Missing required fields: {', '.join(missing_fields)}")
        return None

    print_success("All required fields present")
    print()
    print(f"  Type:             {creds.get('type')}")
    print(f"  Project ID:       {creds.get('project_id')}")
    print(f"  Service Account:  {creds.get('client_email')}")
    print(f"  Private Key ID:   {creds.get('private_key_id', 'N/A')[:20]}...")

    return creds.get('project_id')

def test_firebase_initialization():
    """Test if Firebase Admin SDK can initialize."""
    print_header("Step 5: Test Firebase Initialization")

    try:
        from firebase_admin import credentials, initialize_app, delete_app

        print_info("Attempting to initialize Firebase Admin SDK...")

        # Use Application Default Credentials
        cred = credentials.ApplicationDefault()
        app = initialize_app(cred, name='test-app')

        print_success("Firebase Admin SDK initialized successfully!")
        print_info(f"App name: {app.name}")

        # Clean up
        delete_app(app)
        print_info("Test app deleted (cleanup)")

        return True

    except ImportError:
        print_error("firebase-admin package not installed!")
        print_info("Install with: pip install firebase-admin")
        return False
    except Exception as e:
        print_error(f"Firebase initialization failed: {e}")
        print_info("Common issues:")
        print_info("  - Service account lacks necessary permissions")
        print_info("  - Project ID in credentials doesn't match Firebase project")
        print_info("  - Firebase API not enabled in Google Cloud Console")
        return False

def check_dev_mode():
    """Check DEV_MODE setting."""
    print_header("Step 6: Check DEV_MODE Setting")

    from dotenv import load_dotenv
    load_dotenv()

    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"

    if dev_mode:
        print_success("DEV_MODE is enabled")
        print_info("Authentication is optional for testing")
        print_info("To disable: Set DEV_MODE=false in .env")
    else:
        print_info("DEV_MODE is disabled (production mode)")
        print_info("Authentication is required")
        print_info("To enable: Set DEV_MODE=true in .env")

    return dev_mode

def main():
    """Run all checks."""
    print("\n🔍 Travel Tracker API - Credentials Check")
    print("=" * 60)

    # Step 1: Check environment variable
    creds_path = check_environment_variable()
    if not creds_path:
        print_error("\n❌ Setup incomplete - environment variable not set")
        sys.exit(1)

    # Step 2: Check file exists
    if not check_file_exists(creds_path):
        print_error("\n❌ Setup incomplete - credentials file not found")
        sys.exit(1)

    # Step 3: Read credentials
    creds = read_credentials(creds_path)
    if not creds:
        print_error("\n❌ Setup incomplete - cannot read credentials")
        sys.exit(1)

    # Step 4: Display project info
    project_id = display_project_info(creds)
    if not project_id:
        print_error("\n❌ Setup incomplete - invalid credentials format")
        sys.exit(1)

    # Step 5: Test Firebase
    firebase_ok = test_firebase_initialization()

    # Step 6: Check DEV_MODE
    dev_mode = check_dev_mode()

    # Final summary
    print_header("Summary")

    if firebase_ok:
        print_success("✅ All checks passed!")
        print()
        print(f"  Your backend will connect to:")
        print(f"  📦 Firebase Project: {project_id}")
        print()
        print(f"  Authentication Mode: {'🔧 Development (optional)' if dev_mode else '🔒 Production (required)'}")
        print()
        print(f"  Next steps:")
        print(f"  1. Start your API: uvicorn main:app --reload")
        print(f"  2. Test endpoint: curl http://localhost:8000/health")
        print(f"  3. View docs: http://localhost:8000/docs")
        print()
    else:
        print_error("⚠️  Some checks failed")
        print_info("Fix the issues above and run this script again")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Check interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
