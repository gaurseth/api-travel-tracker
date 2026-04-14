"""
Account lifecycle service — soft-delete request, cancellation, and hard-delete processing.

Flow:
  1. User calls POST /account/delete-request  → sets 3-day countdown
  2. User can call POST /account/cancel-deletion during grace period
  3. Cloud Scheduler calls POST /internal/process-deletions daily
     → hard-deletes accounts past their grace period
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List

from firebase_admin import auth as firebase_auth

from database import (
    get_users_collection,
    get_user_ref,
    get_user_trips_collection,
    get_user_passengers_collection,
)
from services.storage_service import delete_all_user_images


_GRACE_PERIOD_DAYS = 3
_BATCH_LIMIT = 500  # Firestore batch delete limit


class AccountService:

    @staticmethod
    def request_deletion(user_id: str) -> Dict[str, Any]:
        """
        Mark account for deletion after a 3-day grace period.

        Creates/updates the users/{uid} doc with deletion timestamps.
        """
        now = datetime.utcnow()
        scheduled_for = now + timedelta(days=_GRACE_PERIOD_DAYS)

        ref = get_user_ref(user_id)
        ref.set({
            "deletion_requested_at": now.isoformat(),
            "deletion_scheduled_for": scheduled_for.isoformat(),
            "updated_at": now.isoformat(),
        }, merge=True)

        print(f"[Account] Deletion requested for user {user_id}, scheduled for {scheduled_for.isoformat()}")

        return {
            "message": f"Account scheduled for deletion on {scheduled_for.strftime('%Y-%m-%d')}. "
                       f"You have {_GRACE_PERIOD_DAYS} days to cancel.",
            "deletion_requested_at": now.isoformat(),
            "deletion_scheduled_for": scheduled_for.isoformat(),
        }

    @staticmethod
    def cancel_deletion(user_id: str) -> Dict[str, Any]:
        """
        Cancel a pending deletion request during the grace period.

        Clears deletion timestamps from the users/{uid} doc.
        """
        ref = get_user_ref(user_id)
        doc = ref.get()

        if not doc.exists:
            return {"message": "No deletion request found."}

        data = doc.to_dict()
        if not data.get("deletion_requested_at"):
            return {"message": "No deletion request found."}

        ref.update({
            "deletion_requested_at": None,
            "deletion_scheduled_for": None,
            "updated_at": datetime.utcnow().isoformat(),
        })

        print(f"[Account] Deletion cancelled for user {user_id}")
        return {"message": "Account deletion cancelled successfully."}

    @staticmethod
    def get_deletion_status(user_id: str) -> Dict[str, Any]:
        """
        Check if the user has a pending deletion request.
        """
        ref = get_user_ref(user_id)
        doc = ref.get()

        if not doc.exists:
            return {"pending": False}

        data = doc.to_dict()
        scheduled = data.get("deletion_scheduled_for")
        if not scheduled:
            return {"pending": False}

        return {
            "pending": True,
            "deletion_requested_at": data.get("deletion_requested_at"),
            "deletion_scheduled_for": scheduled,
        }

    @staticmethod
    def process_pending_deletions() -> Dict[str, Any]:
        """
        Find all accounts past their grace period and hard-delete them.

        Called by Cloud Scheduler via POST /internal/process-deletions.
        """
        now = datetime.utcnow().isoformat()
        users_coll = get_users_collection()

        query = users_coll.where(
            "deletion_scheduled_for", "<=", now
        ).where(
            "deletion_scheduled_for", "!=", None
        )

        processed = []
        errors = []

        for user_doc in query.stream():
            user_id = user_doc.id
            try:
                AccountService._hard_delete_user(user_id)
                processed.append(user_id)
                print(f"[Account] Hard-deleted user {user_id}")
            except Exception as e:
                errors.append({"user_id": user_id, "error": str(e)})
                print(f"[Account] ERROR deleting user {user_id}: {e}")

        return {
            "processed": len(processed),
            "processed_ids": processed,
            "errors": errors,
        }

    @staticmethod
    def _hard_delete_user(user_id: str) -> None:
        """
        Permanently delete all data for a user:
          1. All passenger docs
          2. All trip docs
          3. All GCS images
          4. The user doc itself
          5. Firebase Auth account
        """
        # 1. Delete all passengers
        passengers_coll = get_user_passengers_collection(user_id)
        _delete_all_docs_in_collection(passengers_coll)

        # 2. Delete all trips
        trips_coll = get_user_trips_collection(user_id)
        _delete_all_docs_in_collection(trips_coll)

        # 3. Delete all images from GCS
        try:
            delete_all_user_images(user_id)
        except Exception as e:
            print(f"[Account] Warning: failed to delete images for {user_id}: {e}")

        # 4. Delete the user document
        get_user_ref(user_id).delete()

        # 5. Delete Firebase Auth account
        try:
            firebase_auth.delete_user(user_id)
            print(f"[Account] Deleted Firebase Auth user {user_id}")
        except firebase_auth.UserNotFoundError:
            print(f"[Account] Firebase Auth user {user_id} not found (already deleted?)")
        except Exception as e:
            print(f"[Account] Warning: failed to delete Firebase Auth user {user_id}: {e}")


def _delete_all_docs_in_collection(coll_ref) -> int:
    """
    Delete all documents in a Firestore collection in batches.
    Returns total number of docs deleted.
    """
    total = 0
    while True:
        docs = list(coll_ref.limit(_BATCH_LIMIT).stream())
        if not docs:
            break
        for doc in docs:
            doc.reference.delete()
        total += len(docs)
    return total
