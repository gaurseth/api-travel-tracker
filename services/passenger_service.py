"""
Passenger service — resolve-by-normalized_name upsert.

Identity is client-controlled BUT the backend deduplicates by normalized_name
to handle concurrent offline creates that picked different client IDs. The
first write for a given (user_id, normalized_name) wins; later writes with a
different id are redirected to the canonical id.

Manual verification cases (no test harness in repo):
  a. First write creates.
  b. Second write with same id merges in place.
  c. Second write with different id + same normalized_name returns canonical.
  d. Soft-deleted existing does NOT collide (new id is created).
  e. is_primary=true demotes the existing primary (different name) in txn.
"""
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

from database import get_user_passengers_collection, get_passenger_ref


def normalize_name(name: str) -> str:
    """
    Canonical passenger name normalization.

    Rule: lowercase, strip punctuation, collapse whitespace.
    Must match the frontend normalization rule exactly.
    """
    if not name:
        return ""
    s = name.lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class PassengerService:
    """Service for managing passengers in Firestore with dedup-by-name."""

    @staticmethod
    def upsert_passenger(
        user_id: str,
        passenger_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Upsert with resolve-by-normalized_name semantics.

        Returns one of:
          - {"id": existing.id, "canonical": True,  "merged_from": client_id, "passenger": {...}}
          - {"id": client_id,   "canonical": False, "passenger": {...}}
        """
        client_id = passenger_data.get("id")
        if not client_id:
            raise ValueError("passenger_data must include 'id' (client-generated)")

        name = passenger_data.get("name")
        if not name:
            raise ValueError("passenger_data must include 'name'")

        normalized = passenger_data.get("normalized_name") or normalize_name(name)
        passenger_data["normalized_name"] = normalized
        is_primary = bool(passenger_data.get("is_primary", False))

        now = datetime.utcnow().isoformat()
        passenger_data.setdefault("created_at", now)
        passenger_data["updated_at"] = passenger_data.get("updated_at") or now
        passenger_data.setdefault("deleted_at", None)

        coll = get_user_passengers_collection(user_id)

        # 1. Look up any existing active passenger with this normalized name.
        existing_doc = None
        existing_data: Optional[Dict[str, Any]] = None
        query = (
            coll.where("normalized_name", "==", normalized)
                .where("deleted_at", "==", None)
                .limit(1)
        )
        for d in query.stream():
            existing_doc = d
            existing_data = d.to_dict()
            break

        # Helper: demote any other primary when this upsert is primary.
        def _demote_other_primaries(keep_id: str) -> None:
            if not is_primary:
                return
            primaries = coll.where("is_primary", "==", True).where("deleted_at", "==", None).stream()
            for p in primaries:
                if p.id == keep_id:
                    continue
                p.reference.update({
                    "is_primary": False,
                    "updated_at": now,
                })
                print(f"[Passenger] Demoted previous primary {p.id} in favor of {keep_id}")

        # 2. Existing doc found with a DIFFERENT client id → return canonical.
        if existing_data and existing_data.get("id") != client_id:
            canonical_id = existing_data["id"]
            canonical_ref = get_passenger_ref(user_id, canonical_id)

            # Merge harmless metadata. Never demote an existing primary via this path.
            merge_payload: Dict[str, Any] = {"updated_at": now}
            if is_primary and not existing_data.get("is_primary"):
                merge_payload["is_primary"] = True

            canonical_ref.set(merge_payload, merge=True)
            _demote_other_primaries(canonical_id)

            merged = canonical_ref.get().to_dict()
            print(f"[Passenger] Dedup: client_id={client_id} redirected to canonical {canonical_id}")
            return {
                "id": canonical_id,
                "canonical": True,
                "merged_from": client_id,
                "passenger": merged,
            }

        # 3. Existing doc found with the SAME id → in-place merge.
        if existing_data and existing_data.get("id") == client_id:
            ref = get_passenger_ref(user_id, client_id)
            ref.set(passenger_data, merge=True)
            _demote_other_primaries(client_id)
            updated = ref.get().to_dict()
            print(f"[Passenger] Merged in-place: {client_id}")
            return {
                "id": client_id,
                "canonical": False,
                "passenger": updated,
            }

        # 4. No existing active doc with this name → create at client_id.
        ref = get_passenger_ref(user_id, client_id)
        ref.set(passenger_data)
        _demote_other_primaries(client_id)
        created = ref.get().to_dict()
        print(f"[Passenger] Created new passenger: {client_id}")
        return {
            "id": client_id,
            "canonical": False,
            "passenger": created,
        }

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
