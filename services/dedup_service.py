"""
Dedup & Multi-Source Merge Service.

Handles deduplication and field-level merging of trip segments arriving
from multiple sources (boarding_pass, manual, email). See DEDUP_MERGE_SPEC.md
for the full specification.
"""
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from database import get_user_trips_collection
from services import TripService


# ---------------------------------------------------------------------------
# Source priority — higher number wins on conflicts
# ---------------------------------------------------------------------------
SOURCE_PRIORITY: Dict[str, int] = {
    "boarding_pass": 1,
    "manual": 2,
    "email": 3,
}

# These fields are overridden: boarding_pass ALWAYS wins regardless of
# overall source priority (day-of-travel data that email doesn't carry).
BOARDING_PASS_WINS_FIELDS = {"seat", "gate", "boarding_time"}


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------

def _normalize_flight_number(raw: str) -> str:
    """
    Strip airline prefix and leading zeros.
    'EK0202' -> '202', '0047' -> '47', 'UA47' -> '47'.
    """
    if not raw:
        return ""
    digits = re.sub(r"[^0-9]", "", raw)
    return digits.lstrip("0") or "0"


def _parse_month_day(date_str: str) -> Optional[Tuple[int, int]]:
    """Extract (month, day) from a YYYY-MM-DD or MM-DD string."""
    if not date_str:
        return None
    try:
        parts = date_str.split("-")
        if len(parts) == 3:
            return int(parts[1]), int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        pass
    return None


def _has_year(date_str: str) -> bool:
    """Check if a date string has a year component."""
    if not date_str:
        return False
    parts = date_str.split("-")
    return len(parts) == 3 and len(parts[0]) == 4


def compute_fingerprint(segment: Dict[str, Any]) -> Optional[str]:
    """
    Compute a canonical fingerprint for a segment.

    Format: 'ORIGIN|DESTINATION|FLIGHT_NUM_DIGITS|MM-DD'
    Returns None if required fields are missing.
    """
    origin = (segment.get("origin") or "").strip().upper()
    dest = (segment.get("destination") or "").strip().upper()
    flight = _normalize_flight_number(segment.get("flight_number") or "")
    dep_date = segment.get("departure_date") or ""

    if not origin or not dest or not flight:
        return None

    md = _parse_month_day(dep_date)
    if not md:
        return None

    return f"{origin}|{dest}|{flight}|{md[0]:02d}-{md[1]:02d}"


def fingerprints_match(fp1: str, fp2: str, date1: str = "", date2: str = "") -> bool:
    """
    Compare two fingerprints. They match if all components are equal.

    Year handling: if both dates have a year and they differ, no match.
    If either is missing a year, month+day match (already in fingerprint) is enough.
    """
    if fp1 != fp2:
        return False

    # Fingerprints match on ORIGIN|DEST|FLIGHT|MM-DD.
    # Extra check: if both have years, years must match.
    if _has_year(date1) and _has_year(date2):
        y1 = date1.split("-")[0]
        y2 = date2.split("-")[0]
        if y1 != y2:
            return False

    return True


# ---------------------------------------------------------------------------
# Search user trips for duplicate segments
# ---------------------------------------------------------------------------

def find_duplicate_segment(
    user_id: str,
    fingerprint: str,
    incoming_date: str,
    incoming_source: str,
) -> Optional[Dict[str, Any]]:
    """
    Search all of the user's trips for a segment matching the given fingerprint.

    Returns:
        {
            "trip_id": str,
            "segment_index": int,       # position in trip["segments"] list
            "segment": dict,            # the matched segment data
            "existing_source": str,     # source of the matched segment
            "is_exact_duplicate": bool, # True if same source type -> reject
        }
        or None if no match.
    """
    trips_ref = get_user_trips_collection(user_id)
    for doc in trips_ref.stream():
        trip = doc.to_dict()
        trip_id = trip.get("trip_id")
        for idx, seg in enumerate(trip.get("segments", [])):
            seg_fp = compute_fingerprint(seg)
            if seg_fp and fingerprints_match(
                seg_fp, fingerprint,
                seg.get("departure_date", ""), incoming_date,
            ):
                existing_source = seg.get("source") or "boarding_pass"
                return {
                    "trip_id": trip_id,
                    "segment_index": idx,
                    "segment": seg,
                    "existing_source": existing_source,
                    "is_exact_duplicate": existing_source == incoming_source,
                }
    return None


def check_boarding_pass_exists(user_id: str, boarding_pass_id: str) -> bool:
    """Check if a boarding_pass_id is already attached to any trip."""
    if not boarding_pass_id:
        return False
    trips_ref = get_user_trips_collection(user_id)
    for doc in trips_ref.stream():
        trip = doc.to_dict()
        for bp in trip.get("boarding_passes", []):
            if bp.get("boarding_pass_id") == boarding_pass_id:
                return True
    return False


# ---------------------------------------------------------------------------
# Field-level merge
# ---------------------------------------------------------------------------

def merge_segment_fields(
    existing: Dict[str, Any],
    incoming: Dict[str, Any],
    existing_source: str,
    incoming_source: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Merge two segments field-by-field using source priority rules.

    Returns: (merged_segment, conflict_log)
    """
    from services.trip_service import _SEGMENT_KEYS

    existing_priority = SOURCE_PRIORITY.get(existing_source, 0)
    incoming_priority = SOURCE_PRIORITY.get(incoming_source, 0)

    merged = dict(existing)  # start from existing
    conflicts: List[Dict[str, Any]] = list(existing.get("conflict_log") or [])
    now = datetime.utcnow().isoformat()

    # Fields to merge — _SEGMENT_KEYS plus provenance fields
    merge_fields = set(_SEGMENT_KEYS) - {"conflict_log", "source"}

    for field in merge_fields:
        existing_val = existing.get(field)
        incoming_val = incoming.get(field)

        # Neither has value
        if not existing_val and not incoming_val:
            continue

        # Only one has value — take it (enrichment)
        if existing_val and not incoming_val:
            continue  # keep existing
        if not existing_val and incoming_val:
            merged[field] = incoming_val
            continue

        # Both have values — check for conflict
        if str(existing_val).strip().upper() == str(incoming_val).strip().upper():
            continue  # same value, no conflict

        # Conflict — determine winner
        if field in BOARDING_PASS_WINS_FIELDS:
            # Boarding pass wins for day-of-travel fields
            if existing_source == "boarding_pass":
                winner_val, loser_val = existing_val, incoming_val
                winner_src, loser_src = existing_source, incoming_source
            elif incoming_source == "boarding_pass":
                winner_val, loser_val = incoming_val, existing_val
                winner_src, loser_src = incoming_source, existing_source
                merged[field] = incoming_val
            else:
                # Neither is boarding_pass — use normal priority
                if incoming_priority >= existing_priority:
                    winner_val, loser_val = incoming_val, existing_val
                    winner_src, loser_src = incoming_source, existing_source
                    merged[field] = incoming_val
                else:
                    winner_val, loser_val = existing_val, incoming_val
                    winner_src, loser_src = existing_source, incoming_source
        elif field == "departure_date":
            # Special: if one side has year and other doesn't, adopt the year
            if _has_year(str(incoming_val)) and not _has_year(str(existing_val)):
                merged[field] = incoming_val
                winner_val, loser_val = incoming_val, existing_val
                winner_src, loser_src = incoming_source, existing_source
            elif _has_year(str(existing_val)) and not _has_year(str(incoming_val)):
                winner_val, loser_val = existing_val, incoming_val
                winner_src, loser_src = existing_source, incoming_source
            elif incoming_priority >= existing_priority:
                merged[field] = incoming_val
                winner_val, loser_val = incoming_val, existing_val
                winner_src, loser_src = incoming_source, existing_source
            else:
                winner_val, loser_val = existing_val, incoming_val
                winner_src, loser_src = existing_source, incoming_source
        else:
            # Normal priority-based resolution
            if incoming_priority >= existing_priority:
                merged[field] = incoming_val
                winner_val, loser_val = incoming_val, existing_val
                winner_src, loser_src = incoming_source, existing_source
            else:
                winner_val, loser_val = existing_val, incoming_val
                winner_src, loser_src = existing_source, incoming_source

        conflicts.append({
            "field": field,
            "kept": str(winner_val),
            "discarded": str(loser_val),
            "kept_source": winner_src,
            "discarded_source": loser_src,
            "timestamp": now,
        })

    # Set source to the highest-priority contributor
    if incoming_priority >= existing_priority:
        merged["source"] = incoming_source
    else:
        merged["source"] = existing_source

    merged["conflict_log"] = conflicts
    return merged, conflicts


# ---------------------------------------------------------------------------
# Ingest orchestrator
# ---------------------------------------------------------------------------

def ingest_segments(
    user_id: str,
    segments: List[Dict[str, Any]],
    source: str,
    passenger_id: Optional[str] = None,
    passenger_name: Optional[str] = None,
    boarding_pass_id: Optional[str] = None,
    raw_text: Optional[str] = None,
    extraction_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Unified ingest pipeline for all sources.

    Steps:
      1. Check boarding_pass_id for re-scan duplicate
      2. Fingerprint each incoming segment
      3. For each segment, search for duplicates:
         a. Exact duplicate (same source) -> reject
         b. Cross-source match -> merge fields
         c. No match -> collect as new
      4. For new/merged segments, find or create trip:
         a. If any merged into existing trip -> use that trip
         b. Else find_matching_trip() for route chaining
         c. Else create new trip

    Returns:
      {
        "action": "created" | "merged" | "rejected",
        "trip_id": str or None,
        "segments_merged": int,
        "segments_added": int,
        "segments_rejected": int,
        "conflicts": list,
        "details": str,
      }
    """
    # Tag all incoming segments with source
    for seg in segments:
        seg["source"] = source
        if passenger_id:
            seg.setdefault("passenger_id", passenger_id)
        if not seg.get("conflict_log"):
            seg["conflict_log"] = []

    # Step 1: boarding pass re-scan check
    if boarding_pass_id and check_boarding_pass_exists(user_id, boarding_pass_id):
        print(f"[Dedup] Rejected: boarding_pass_id {boarding_pass_id} already exists")
        return {
            "action": "rejected",
            "trip_id": None,
            "segments_merged": 0,
            "segments_added": 0,
            "segments_rejected": len(segments),
            "conflicts": [],
            "details": f"Boarding pass {boarding_pass_id} already processed.",
        }

    # Step 2-3: fingerprint and search for duplicates
    merged_trip_id = None
    merged_count = 0
    rejected_count = 0
    new_segments: List[Dict[str, Any]] = []
    all_conflicts: List[Dict[str, Any]] = []

    for seg in segments:
        fp = compute_fingerprint(seg)
        if not fp:
            # Can't fingerprint (missing fields) — treat as new
            new_segments.append(seg)
            continue

        dup = find_duplicate_segment(
            user_id, fp,
            seg.get("departure_date", ""),
            source,
        )

        if not dup:
            # No match — new segment
            new_segments.append(seg)
            continue

        if dup["is_exact_duplicate"]:
            # Same source type — reject
            rejected_count += 1
            print(f"[Dedup] Rejected exact duplicate: {fp} (source={source})")
            continue

        # Cross-source match — merge fields into the existing segment
        existing_seg = dup["segment"]
        existing_source = dup["existing_source"]
        trip_id = dup["trip_id"]
        seg_idx = dup["segment_index"]

        merged_seg, conflicts = merge_segment_fields(
            existing_seg, seg, existing_source, source,
        )
        all_conflicts.extend(conflicts)

        # Write merged segment back to the trip
        _update_segment_in_trip(user_id, trip_id, seg_idx, merged_seg)
        merged_trip_id = trip_id
        merged_count += 1

        if conflicts:
            print(f"[Dedup] Merged {fp} into trip {trip_id} with {len(conflicts)} conflict(s)")
        else:
            print(f"[Dedup] Enriched {fp} into trip {trip_id} (no conflicts)")

    # Step 4: handle new segments
    added_count = 0
    result_trip_id = merged_trip_id

    if new_segments:
        if merged_trip_id:
            # Attach new segments to the same trip we merged into
            TripService.attach_segments_to_trip(
                user_id=user_id,
                trip_id=merged_trip_id,
                segments=new_segments,
                passenger_id=passenger_id,
                passenger_name=passenger_name,
                raw_text=raw_text,
                extraction_metadata=extraction_metadata,
            )
            result_trip_id = merged_trip_id
            added_count = len(new_segments)
        else:
            # Try find_matching_trip for route chaining
            match = TripService.find_matching_trip(user_id, new_segments)
            if match:
                TripService.attach_segments_to_trip(
                    user_id=user_id,
                    trip_id=match["trip_id"],
                    segments=new_segments,
                    passenger_id=passenger_id,
                    passenger_name=passenger_name,
                    raw_text=raw_text,
                    extraction_metadata=extraction_metadata,
                )
                result_trip_id = match["trip_id"]
                added_count = len(new_segments)
            else:
                # Create new trip
                result = TripService.create_trip_from_segments(
                    user_id=user_id,
                    tenant_id="personal",
                    segments=new_segments,
                    passenger_id=passenger_id,
                    passenger_name=passenger_name,
                    raw_text=raw_text,
                    extraction_metadata=extraction_metadata,
                )
                result_trip_id = result.get("trip_id")
                added_count = len(new_segments)

    # Determine overall action
    if rejected_count == len(segments):
        action = "rejected"
    elif merged_count > 0:
        action = "merged"
    else:
        action = "created"

    return {
        "action": action,
        "trip_id": result_trip_id,
        "segments_merged": merged_count,
        "segments_added": added_count,
        "segments_rejected": rejected_count,
        "conflicts": all_conflicts,
        "details": (
            f"{merged_count} merged, {added_count} added, "
            f"{rejected_count} rejected, {len(all_conflicts)} conflict(s)"
        ),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _update_segment_in_trip(
    user_id: str,
    trip_id: str,
    segment_index: int,
    merged_segment: Dict[str, Any],
) -> None:
    """Write a merged segment back into its trip document."""
    from database import get_trip_ref

    trip_ref = get_trip_ref(user_id, trip_id)
    doc = trip_ref.get()
    if not doc.exists:
        print(f"[Dedup] WARNING: trip {trip_id} not found for segment update")
        return

    trip = doc.to_dict()
    segments = trip.get("segments", [])
    if segment_index < len(segments):
        segments[segment_index] = merged_segment
        trip_ref.update({
            "segments": segments,
            "updated_at": datetime.utcnow().isoformat(),
        })
