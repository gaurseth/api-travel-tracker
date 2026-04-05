"""
Passenger service — upsert-by-ID operations.

Backend is a dumb upsert system. All identity is client-controlled:
- IDs are generated ONLY on the frontend
- Backend never generates, infers, or replaces IDs
- Backend never searches/matches by name
"""
from datetime import datetime
from typing import Dict, Any, List, Optional

from database import get_user_passengers_collection, get_passenger_ref


class PassengerService:
    """Service for managing passengers in Firestore via client-provided IDs."""

    @staticmethod
    def upsert_passenger(
        user_id: str,
        passenger_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Upsert a passenger using the client-provided ID.

        - If document exists: merge/update fields
        - If document does not exist: create with provided ID

        Args:
            user_id: The authenticated user's ID
            passenger_data: Must include 'id'. May include name, normalized_name,
                           is_primary, updated_at, etc.

        Returns:
            {"passenger_id": str, "action": "created" | "updated"}
        """
        passenger_id = passenger_data.get("id")
        if not passenger_id:
            raise ValueError("passenger_data must include 'id' (client-generated)")

        ref = get_passenger_ref(user_id, passenger_id)

        # Ensure timestamps
        now = datetime.utcnow().isoformat()
        passenger_data.setdefault("created_at", now)
        passenger_data.setdefault("updated_at", now)
        passenger_data.setdefault("deleted_at", None)

        doc = ref.get()
        if doc.exists:
            # Update — merge fields
            ref.set(passenger_data, merge=True)
            print(f"[Passenger] Updated existing passenger: {passenger_id}")
            return {"passenger_id": passenger_id, "action": "updated"}
        else:
            # Create — use provided ID as document ID
            ref.set(passenger_data)
            print(f"[Passenger] Created new passenger: {passenger_id}")
            return {"passenger_id": passenger_id, "action": "created"}

    @staticmethod
    def list_passengers(user_id: str) -> List[Dict[str, Any]]:
        """List all active (non-deleted) passengers for a user."""
        coll = get_user_passengers_collection(user_id)
        docs = coll.where("deleted_at", "==", None).stream()
        return [d.to_dict() for d in docs]

    @staticmethod
    def get_passenger(user_id: str, passenger_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific passenger by ID."""
        ref = get_passenger_ref(user_id, passenger_id)
        doc = ref.get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        if data.get("deleted_at"):
            return None
        return data

    @staticmethod
    def update_passenger(
        user_id: str,
        passenger_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        """
        Update a passenger's fields.
        Returns False if passenger not found or deleted.
        """
        ref = get_passenger_ref(user_id, passenger_id)
        doc = ref.get()
        if not doc.exists:
            return False
        data = doc.to_dict()
        if data.get("deleted_at"):
            return False

        updates["updated_at"] = datetime.utcnow().isoformat()
        ref.update(updates)
        return True

    @staticmethod
    def delete_passenger(user_id: str, passenger_id: str) -> bool:
        """Soft-delete a passenger by setting deleted_at."""
        ref = get_passenger_ref(user_id, passenger_id)
        doc = ref.get()
        if not doc.exists:
            return False
        data = doc.to_dict()
        if data.get("deleted_at"):
            return False

        ref.update({
            "deleted_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        })
        return True
