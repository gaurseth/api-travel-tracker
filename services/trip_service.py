"""
Trip service for managing trips in Firestore with multi-segment support.
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import re
import uuid
from google.cloud import firestore

from models.boarding_pass import BoardingPass
from models.common import Warning
from database import get_user_trips_collection, get_trip_ref
import os
from services.flight_helpers import estimate_flight_distance, get_trip_type, estimate_travel_time
from services.aviationstack_service import lookup_flight_schedule as aviationstack_lookup
from services.aerodatabox_service import lookup_flight_schedule as aerodatabox_lookup


def _get_flight_lookup_fn():
    """Return the active flight schedule lookup function based on FLIGHT_API env var."""
    api = os.getenv("FLIGHT_API", "aviationstack").lower()
    if api == "aerodatabox":
        return aerodatabox_lookup, "AeroDataBox"
    return aviationstack_lookup, "Aviationstack"


# Keys present in every flat segment dict produced by conversion helpers
_SEGMENT_KEYS = (
    "origin", "destination", "airline_code", "flight_number",
    "departure_date", "departure_time", "arrival_date", "arrival_time",
    "seat", "gate", "boarding_time", "pnr", "cabin_class", "passenger_name",
    "passenger_id", "ticket_number", "aircraft",
    "departure_terminal", "arrival_terminal", "source", "conflict_log",
)


class TripService:
    """Service for managing trips in Firestore with multi-segment support."""

    @staticmethod
    def generate_trip_id() -> str:
        return f"trip_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _generate_boarding_pass_id() -> str:
        return f"bp_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _compute_derived_fields(segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Derive trip-level origin, destination, departure_date and arrival_date
        from the outward segments only.

        - origin / departure_date  → first outward segment
        - destination / arrival_date → last outward segment
        """
        outward = [s for s in segments if s.get("journey_type") == "outward"]

        if not outward:
            return {"origin": None, "destination": None,
                    "departure_date": None, "arrival_date": None}

        return {
            "origin":         outward[0].get("origin"),
            "departure_date": outward[0].get("departure_date"),
            "destination":    outward[-1].get("destination"),
            "arrival_date":   outward[-1].get("arrival_date"),
        }

    @staticmethod
    def _generate_title(segments: List[Dict[str, Any]]) -> str:
        """Auto-generate a human-readable trip title from outward segments."""
        outward = [s for s in segments if s.get("journey_type") == "outward"]
        if not outward:
            return "Trip"

        # Build route chain: A → B → C
        stops = [outward[0].get("origin") or "?"] + \
                [s.get("destination") or "?" for s in outward]
        title = " → ".join(stops)

        # Prefix with flight number for single-leg trips
        if len(outward) == 1:
            airline = outward[0].get("airline_code", "")
            flight  = outward[0].get("flight_number", "")
            if airline and flight:
                title = f"{airline}{flight}: {title}"

        return title

    @staticmethod
    def _enrich_segment(seg: Dict[str, Any]) -> Dict[str, Any]:
        """Compute distance, duration, type from origin/destination. Look up flight schedule if times missing."""
        origin = seg.get("origin")
        dest = seg.get("destination")
        if origin and dest:
            seg["distance_miles"] = estimate_flight_distance(origin, dest)
            seg["travel_duration_minutes"] = estimate_travel_time(origin, dest)
            seg["segment_type"] = get_trip_type(origin, dest)
        else:
            seg["distance_miles"] = None
            seg["travel_duration_minutes"] = None
            seg["segment_type"] = None

        # Aviationstack enrichment — fill missing times from real flight schedules
        has_times = seg.get("departure_time") and seg.get("arrival_time")
        has_flight_info = seg.get("airline_code") and seg.get("flight_number")
        print(f"[Enrich] Segment: {seg.get('origin')}->{seg.get('destination')} "
              f"airline={seg.get('airline_code')} flight={seg.get('flight_number')} "
              f"dep_time={seg.get('departure_time')} arr_time={seg.get('arrival_time')} "
              f"has_times={has_times} has_flight_info={has_flight_info}")

        if not has_times and has_flight_info:
            lookup_fn, api_name = _get_flight_lookup_fn()
            print(f"[Enrich] Times missing + flight info present — calling {api_name}")
            schedule = lookup_fn(
                airline_code=seg["airline_code"],
                flight_number=seg["flight_number"],
                origin=seg.get("origin"),
                destination=seg.get("destination"),
                departure_date=seg.get("departure_date"),
            )
            if schedule:
                print(f"[Enrich] Got schedule from {api_name}: {schedule}")
                if not seg.get("departure_time"):
                    seg["departure_time"] = schedule.get("departure_time")
                if not seg.get("arrival_time"):
                    seg["arrival_time"] = schedule.get("arrival_time")
                if not seg.get("arrival_date"):
                    seg["arrival_date"] = schedule.get("arrival_date")
                seg["departure_timezone"] = schedule.get("departure_timezone")
                seg["arrival_timezone"] = schedule.get("arrival_timezone")
            else:
                print(f"[Enrich] {api_name} returned None — no time enrichment")
        elif has_times:
            print("[Enrich] Times already present — skipping flight API")
        elif not has_flight_info:
            print("[Enrich] No airline_code/flight_number — skipping flight API")

        return seg

    @staticmethod
    def _create_segments_from_boarding_pass(
        boarding_pass: BoardingPass,
        boarding_pass_id: str,
        journey_type: str = "outward"
    ) -> List[Dict[str, Any]]:
        """
        Convert boarding pass segments into trip segment dicts.

        Args:
            boarding_pass: Parsed boarding pass (may have multiple segments)
            boarding_pass_id: ID of the parent boarding pass attachment
            journey_type: "outward" or "return" — applied to all segments from this pass
        """
        trip_segments = []

        for bp_seg in boarding_pass.segments:
            trip_segment = {
                "segment_number":       bp_seg.segment_number,
                "journey_type":         journey_type,

                # Route
                "origin":      bp_seg.route.origin.iata.value if bp_seg.route.origin.iata.value else None,
                "destination": bp_seg.route.destination.iata.value if bp_seg.route.destination.iata.value else None,

                # Schedule
                "departure_date": bp_seg.schedule.departure_date.value if bp_seg.schedule and bp_seg.schedule.departure_date else None,
                "departure_time": bp_seg.schedule.departure_time.value if bp_seg.schedule and bp_seg.schedule.departure_time else None,
                "arrival_date":   bp_seg.schedule.arrival_date.value   if bp_seg.schedule and bp_seg.schedule.arrival_date   else None,
                "arrival_time":   bp_seg.schedule.arrival_time.value   if bp_seg.schedule and bp_seg.schedule.arrival_time   else None,

                # Flight
                "airline_code":     bp_seg.flight.airline_code.value  if bp_seg.flight.airline_code.value  else None,
                "flight_number":    bp_seg.flight.flight_number.value if bp_seg.flight.flight_number.value else None,
                "operating_carrier": None,

                # Boarding
                "seat":          bp_seg.boarding.seat.value  if bp_seg.boarding and bp_seg.boarding.seat  else None,
                "gate":          bp_seg.boarding.gate.value  if bp_seg.boarding and bp_seg.boarding.gate  else None,
                "boarding_time": bp_seg.boarding.time.value  if bp_seg.boarding and bp_seg.boarding.time  else None,

                # Reference
                "boarding_pass_id":       boarding_pass_id,
                "segment_index_in_pass":  bp_seg.segment_number - 1,

                # Booking
                "pnr":         boarding_pass.pnr.value if boarding_pass.pnr else None,
                "cabin_class": None,

                # Passenger
                "passenger_name": (
                    boarding_pass.passenger.full_name.value
                    if boarding_pass.passenger.full_name else None
                ),

                # Metadata
                "manually_entered": False,
                "notes":            None,
            }
            TripService._enrich_segment(trip_segment)
            trip_segments.append(trip_segment)

        return trip_segments

    @staticmethod
    def _insert_segment_ordered(
        existing_segments: List[Dict[str, Any]],
        new_segment: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Insert new_segment into existing_segments at the correct position
        based on route chaining, then renumber all segment_numbers.

        Matching is scoped to the same journey_type group so return segments
        are never inserted into the middle of outward segments and vice versa.
        Return segments always follow all outward segments in the final order.

        Priority:
          1. new.destination == existing.origin  → insert BEFORE that segment
          2. new.origin      == existing.destination → insert AFTER that segment
          3. No match → append to end of the same-journey_type group
        """
        journey_type = new_segment.get("journey_type", "outward")

        # Segments missing journey_type are treated as "outward" (backward compatibility)
        def _jtype(seg: Dict[str, Any]) -> str:
            return seg.get("journey_type") or "outward"

        # Normalise an IATA code for comparison (uppercase, stripped)
        def _norm(code) -> str:
            return code.strip().upper() if code else ""

        # Split into journey groups (preserve existing order within each group)
        outward = [s for s in existing_segments if _jtype(s) == "outward"]
        return_ = [s for s in existing_segments if _jtype(s) == "return"]

        group = outward if journey_type == "outward" else return_

        new_origin = _norm(new_segment.get("origin"))
        new_dest   = _norm(new_segment.get("destination"))
        insert_at  = None

        # Case 1: new segment leads into an existing segment
        for i, seg in enumerate(group):
            if new_dest and _norm(seg.get("origin")) == new_dest:
                insert_at = i
                break

        # Case 2: new segment follows an existing segment
        if insert_at is None:
            for i, seg in enumerate(group):
                if new_origin and _norm(seg.get("destination")) == new_origin:
                    insert_at = i + 1
                    break

        # Case 3: no route match — append
        if insert_at is None:
            group.append(new_segment)
        else:
            group.insert(insert_at, new_segment)

        # Reconstruct: outward always before return
        all_segments = (group + return_) if journey_type == "outward" else (outward + group)

        # Renumber sequentially from 1
        for idx, seg in enumerate(all_segments, start=1):
            seg["segment_number"] = idx

        return all_segments

    # ------------------------------------------------------------------
    # Segment conversion helpers (extraction → flat dicts)
    # ------------------------------------------------------------------

    @staticmethod
    def bcbp_data_to_segment_dicts(bcbp_data: dict) -> List[Dict[str, Any]]:
        """
        Convert raw BCBPParser.parse() output to flat segment dicts.
        Used by /extract-from-scan and /process-boarding-pass.
        """
        passenger_name = bcbp_data.get("passenger_name")
        top_pnr = bcbp_data.get("pnr")

        segments = []
        for seg in bcbp_data.get("segments", []):
            segments.append({
                "origin":          seg.get("origin"),
                "destination":     seg.get("destination"),
                "airline_code":    seg.get("airline_code"),
                "flight_number":   seg.get("flight_number"),
                "departure_date":  seg.get("departure_date"),
                "departure_time":  None,
                "arrival_date":    None,
                "arrival_time":    None,
                "seat":            seg.get("seat"),
                "gate":            None,
                "boarding_time":   None,
                "pnr":             seg.get("pnr") or top_pnr,
                "cabin_class":     seg.get("cabin_class"),
                "passenger_name":  passenger_name,
            })
        return segments

    @staticmethod
    def boarding_pass_to_segment_dicts(boarding_pass: BoardingPass) -> List[Dict[str, Any]]:
        """
        Convert OCR-parsed BoardingPass model to flat segment dicts.
        Used by /extract-from-image and /process-boarding-pass.
        """
        pnr_val = boarding_pass.pnr.value if boarding_pass.pnr else None
        passenger_name = (
            boarding_pass.passenger.full_name.value
            if boarding_pass.passenger.full_name else None
        )

        segments = []
        for bp_seg in boarding_pass.segments:
            segments.append({
                "origin":         bp_seg.route.origin.iata.value if bp_seg.route.origin.iata and bp_seg.route.origin.iata.value else None,
                "destination":    bp_seg.route.destination.iata.value if bp_seg.route.destination.iata and bp_seg.route.destination.iata.value else None,
                "airline_code":   bp_seg.flight.airline_code.value if bp_seg.flight.airline_code and bp_seg.flight.airline_code.value else None,
                "flight_number":  bp_seg.flight.flight_number.value if bp_seg.flight.flight_number and bp_seg.flight.flight_number.value else None,
                "departure_date": bp_seg.schedule.departure_date.value if bp_seg.schedule and bp_seg.schedule.departure_date else None,
                "departure_time": bp_seg.schedule.departure_time.value if bp_seg.schedule and bp_seg.schedule.departure_time else None,
                "arrival_date":   bp_seg.schedule.arrival_date.value if bp_seg.schedule and bp_seg.schedule.arrival_date else None,
                "arrival_time":   bp_seg.schedule.arrival_time.value if bp_seg.schedule and bp_seg.schedule.arrival_time else None,
                "seat":           bp_seg.boarding.seat.value if bp_seg.boarding and bp_seg.boarding.seat else None,
                "gate":           bp_seg.boarding.gate.value if bp_seg.boarding and bp_seg.boarding.gate else None,
                "boarding_time":  bp_seg.boarding.time.value if bp_seg.boarding and bp_seg.boarding.time else None,
                "pnr":            pnr_val,
                "cabin_class":    None,
                "passenger_name": passenger_name,
            })
        return segments

    # ------------------------------------------------------------------
    # Field validation helpers (Guardrail 3)
    # ------------------------------------------------------------------

    _IATA_RE = re.compile(r"^[A-Z]{3}$")
    _DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    _TIME_RE = re.compile(r"^\d{2}:\d{2}$")
    _FLIGHT_NUM_RE = re.compile(r"^\d{1,5}[A-Z]?$")

    @staticmethod
    def _validate_ocr_field(key: str, value) -> bool:
        """
        Guardrail 3: Sanity-check an OCR-extracted field value before merge.
        Returns True if the value is acceptable, False if it should be discarded.
        """
        if value is None:
            return True  # nothing to validate

        val = str(value).strip()
        if not val:
            return True

        if key in ("origin", "destination"):
            return bool(TripService._IATA_RE.match(val.upper()))

        if key in ("departure_date", "arrival_date"):
            if not TripService._DATE_RE.match(val):
                return False
            try:
                d = datetime.fromisoformat(val)
                # reject dates more than 2 years in the past or future
                now = datetime.utcnow()
                return abs((d - now).days) < 730
            except ValueError:
                return False

        if key in ("departure_time", "arrival_time", "boarding_time"):
            return bool(TripService._TIME_RE.match(val))

        if key == "flight_number":
            return bool(TripService._FLIGHT_NUM_RE.match(val.upper()))

        if key == "airline_code":
            # 2-3 uppercase alphanumeric chars
            return bool(re.match(r"^[A-Z0-9]{2,3}$", val.upper()))

        # For other fields (seat, gate, pnr, cabin_class, passenger_name) — accept as-is
        return True

    # ------------------------------------------------------------------
    # Segment merge
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_segments(
        barcode_segments: List[Dict[str, Any]],
        ocr_segments: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Merge barcode-extracted and OCR-extracted segments with guardrails.

        Guardrails (when barcode is present):
          1. Segment count cap: OCR cannot produce more segments than barcode.
             Extra OCR segments are dropped.
          2. Route validation: Only merge OCR segments whose origin+destination
             match a barcode segment. Unmatched OCR segments are discarded.
          3. Field sanity: OCR values are validated before merging (IATA codes,
             dates, times, flight numbers). Invalid values are dropped.

        When barcode_segments is empty (OCR-only mode), guardrails 1-2 are
        skipped and only field sanity (3) is applied.

        Returns:
            (merged_segments, warnings) — warnings list describes any
            discarded data for transparency.
        """
        warnings: List[str] = []

        # OCR-only mode: apply field sanity checks only
        if not barcode_segments:
            sanitised = []
            for seg in ocr_segments:
                clean = {}
                for key in _SEGMENT_KEYS:
                    val = seg.get(key)
                    if TripService._validate_ocr_field(key, val):
                        clean[key] = val
                    else:
                        clean[key] = None
                        warnings.append(f"OCR field '{key}' discarded (invalid: {val!r})")
                sanitised.append(clean)
            return sanitised, warnings

        def _norm(val):
            return val.strip().upper() if val else ""

        # --- Guardrail 1: cap OCR segment count to barcode count ---
        barcode_count = len(barcode_segments)
        capped_ocr = ocr_segments[:barcode_count]
        if len(ocr_segments) > barcode_count:
            dropped = len(ocr_segments) - barcode_count
            warnings.append(
                f"Guardrail: dropped {dropped} extra OCR segment(s) "
                f"(barcode has {barcode_count})"
            )

        # --- Guardrail 2 + 3: route-match then field-validate ---
        ocr_used: set = set()
        merged: List[Dict[str, Any]] = []

        for bs in barcode_segments:
            # Find a matching OCR segment by route
            match_idx = None
            for j, os_ in enumerate(capped_ocr):
                if j in ocr_used:
                    continue
                if (_norm(bs.get("origin")) == _norm(os_.get("origin"))
                        and _norm(bs.get("destination")) == _norm(os_.get("destination"))):
                    match_idx = j
                    break

            if match_idx is not None:
                ocr_used.add(match_idx)
                os_ = capped_ocr[match_idx]
                # Merge field by field: barcode wins; OCR fills gaps with validation
                combined = {}
                for key in _SEGMENT_KEYS:
                    bc_val = bs.get(key)
                    ocr_val = os_.get(key)

                    if bc_val is not None:
                        # Barcode value exists — use it (Guardrail 5: barcode is truth)
                        if ocr_val is not None and _norm(str(bc_val)) != _norm(str(ocr_val)):
                            warnings.append(
                                f"Field '{key}' conflict: barcode={bc_val!r} vs OCR={ocr_val!r}, keeping barcode"
                            )
                        combined[key] = bc_val
                    elif ocr_val is not None:
                        # Only OCR has a value — validate before accepting
                        if TripService._validate_ocr_field(key, ocr_val):
                            combined[key] = ocr_val
                        else:
                            combined[key] = None
                            warnings.append(f"OCR field '{key}' discarded (invalid: {ocr_val!r})")
                    else:
                        combined[key] = None

                merged.append(combined)
            else:
                # No OCR match — use barcode segment as-is
                merged.append(dict(bs))

        # Guardrail 2: discard unmatched OCR segments (route didn't match any barcode segment)
        for j, os_ in enumerate(capped_ocr):
            if j not in ocr_used:
                route = f"{os_.get('origin', '?')}->{os_.get('destination', '?')}"
                warnings.append(
                    f"Guardrail: discarded OCR segment {j+1} (route {route} "
                    f"doesn't match any barcode segment)"
                )

        return merged, warnings

    # ------------------------------------------------------------------
    # Trip matching
    # ------------------------------------------------------------------

    @staticmethod
    def find_matching_trip(
        user_id: str,
        segments: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Find an existing trip that the new segments likely belong to.

        Query: trips where arrival_date is within ±3 days of the first
               new segment's departure_date.
        Scoring (tiered):
            +50  Same PNR
            +30  Route continuity (trip destination == new segment origin)
            +20  Time gap ≤ 24 h
            +10  Time gap 24–48 h  (mutually exclusive with +20)

        Returns {"trip_id": str, "score": int} if best score ≥ 40, else None.
        """
        first_dep = segments[0].get("departure_date") if segments else None
        if not first_dep:
            return None

        try:
            dep_date = datetime.fromisoformat(first_dep)
        except ValueError:
            return None

        date_min = (dep_date - timedelta(days=3)).strftime("%Y-%m-%d")
        date_max = (dep_date + timedelta(days=3)).strftime("%Y-%m-%d")

        # Query trips whose arrival_date is near the new segment's departure
        trips_ref = get_user_trips_collection(user_id)
        candidates = list(
            trips_ref
            .where("arrival_date", ">=", date_min)
            .where("arrival_date", "<=", date_max)
            .stream()
        )

        if not candidates:
            return None

        new_pnrs = {s.get("pnr").strip().upper() for s in segments if s.get("pnr")}
        new_origin = segments[0].get("origin", "").strip().upper() if segments[0].get("origin") else ""

        best_trip_id = None
        best_score = 0

        for doc in candidates:
            trip = doc.to_dict()
            score = 0

            # --- PNR match ---
            existing_pnrs: set = set()
            for seg in trip.get("segments", []):
                if seg.get("pnr"):
                    existing_pnrs.add(seg["pnr"].strip().upper())
            # Also check boarding pass attachments for PNR
            for bp in trip.get("boarding_passes", []):
                bp_data = bp.get("boarding_pass_data", {})
                if bp_data.get("pnr") and isinstance(bp_data["pnr"], dict):
                    pnr_val = bp_data["pnr"].get("value")
                    if pnr_val:
                        existing_pnrs.add(pnr_val.strip().upper())

            if new_pnrs & existing_pnrs:
                score += 50

            # --- Route continuity ---
            trip_dest = (trip.get("destination") or "").strip().upper()
            if trip_dest and new_origin and trip_dest == new_origin:
                score += 30

            # --- Time gap ---
            trip_arrival = trip.get("arrival_date")
            if trip_arrival:
                try:
                    arr = datetime.fromisoformat(trip_arrival)
                    gap_hours = abs((dep_date - arr).total_seconds()) / 3600
                    if gap_hours <= 24:
                        score += 20
                    elif gap_hours <= 48:
                        score += 10
                except ValueError:
                    pass

            if score > best_score:
                best_score = score
                best_trip_id = trip.get("trip_id")

        if best_score >= 40 and best_trip_id:
            return {"trip_id": best_trip_id, "score": best_score}

        return None

    # ------------------------------------------------------------------
    # Create / attach from flat segment dicts
    # ------------------------------------------------------------------

    @staticmethod
    def create_trip_from_segments(
        user_id: str,
        tenant_id: str,
        segments: List[Dict[str, Any]],
        journey_type: str = "outward",
        passenger_name: Optional[str] = None,
        passenger_id: Optional[str] = None,
        extraction_metadata: Optional[Dict[str, Any]] = None,
        raw_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new trip from pre-flattened segment dicts.
        Used by /process-boarding-pass after merge.
        """
        trip_id          = TripService.generate_trip_id()
        boarding_pass_id = TripService._generate_boarding_pass_id()
        created_at       = datetime.utcnow()

        # Prepare segment dicts with trip-specific fields
        trip_segments = []
        for idx, seg in enumerate(segments):
            trip_seg = {
                **{k: seg.get(k) for k in _SEGMENT_KEYS},
                "segment_number":        idx + 1,
                "journey_type":          journey_type,
                "operating_carrier":     None,
                "boarding_pass_id":      boarding_pass_id,
                "segment_index_in_pass": idx,
                "manually_entered":      False,
                "notes":                 None,
            }
            # Propagate passenger_id to all segments
            if passenger_id:
                trip_seg["passenger_id"] = passenger_id
            TripService._enrich_segment(trip_seg)
            trip_segments.append(trip_seg)

        derived = TripService._compute_derived_fields(trip_segments)

        if not passenger_name:
            passenger_name = segments[0].get("passenger_name") if segments else None

        # Build normalized name for boarding pass attachment
        raw_pax_name = passenger_name or ""
        normalized_pax = None  # normalization is client-controlled

        bp_attachment = {
            "boarding_pass_id":    boarding_pass_id,
            "passenger_id":        passenger_id,
            "raw_passenger_name":  raw_pax_name or None,
            "normalized_name":     normalized_pax,
            "boarding_pass_data":  {},
            "segment_count":       len(segments),
            "attached_at":         created_at.isoformat(),
            "extraction_metadata": extraction_metadata or {},
            "raw_ocr_text":        raw_text,
        }

        trip_data = {
            "trip_id":          trip_id,
            "user_id":          user_id,
            "tenant_id":        tenant_id,
            "trip_type":        "flight",
            "created_at":       created_at,
            "updated_at":       created_at,
            "segments":         trip_segments,
            "boarding_passes":  [bp_attachment],
            "passenger_name":   passenger_name,
            **derived,
            "title":            TripService._generate_title(trip_segments),
            "description":      None,
            "notes":            None,
            "tags":             [],
            "user_corrections": [],
            "metadata": {
                "created_at": created_at.isoformat(),
                "updated_at": created_at.isoformat(),
                "source":     "boarding_pass_scan",
                "extraction_metadata": extraction_metadata or {},
            },
        }

        get_trip_ref(user_id, trip_id).set(trip_data)
        return {"trip_id": trip_id, "created_at": created_at.isoformat()}

    @staticmethod
    def attach_segments_to_trip(
        user_id: str,
        trip_id: str,
        segments: List[Dict[str, Any]],
        journey_type: str = "outward",
        passenger_id: Optional[str] = None,
        passenger_name: Optional[str] = None,
        extraction_metadata: Optional[Dict[str, Any]] = None,
        raw_text: Optional[str] = None,
    ) -> bool:
        """
        Attach pre-flattened segment dicts to an existing trip.
        Uses _insert_segment_ordered for route chaining, recomputes derived fields.
        """
        trip_ref = get_trip_ref(user_id, trip_id)
        trip_doc = trip_ref.get()
        if not trip_doc.exists:
            return False

        trip_data        = trip_doc.to_dict()
        boarding_pass_id = TripService._generate_boarding_pass_id()
        current_time     = datetime.utcnow()

        all_segments = trip_data.get("segments", [])
        for idx, seg in enumerate(segments):
            new_seg = {
                **{k: seg.get(k) for k in _SEGMENT_KEYS},
                "segment_number":        0,  # assigned by _insert_segment_ordered
                "journey_type":          journey_type,
                "operating_carrier":     None,
                "boarding_pass_id":      boarding_pass_id,
                "segment_index_in_pass": idx,
                "manually_entered":      False,
                "notes":                 None,
            }
            if passenger_id:
                new_seg["passenger_id"] = passenger_id
            TripService._enrich_segment(new_seg)
            all_segments = TripService._insert_segment_ordered(all_segments, new_seg)

        raw_pax_name = passenger_name or (segments[0].get("passenger_name") if segments else None)
        normalized_pax = None  # normalization is client-controlled

        bp_attachment = {
            "boarding_pass_id":    boarding_pass_id,
            "passenger_id":        passenger_id,
            "raw_passenger_name":  raw_pax_name,
            "normalized_name":     normalized_pax,
            "boarding_pass_data":  {},
            "segment_count":       len(segments),
            "attached_at":         current_time.isoformat(),
            "extraction_metadata": extraction_metadata or {},
            "raw_ocr_text":        raw_text,
        }

        derived = TripService._compute_derived_fields(all_segments)

        trip_ref.update({
            "segments":        all_segments,
            "boarding_passes": trip_data.get("boarding_passes", []) + [bp_attachment],
            "updated_at":      current_time,
            **derived,
        })
        return True

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    @staticmethod
    def create_trip_from_boarding_pass(
        user_id: str,
        tenant_id: str,
        boarding_pass: BoardingPass,
        overall_confidence: float,
        quality_label: str,
        warnings: List[Warning],
        raw_text: str,
        extraction_method: str = "rules"
    ) -> Dict[str, Any]:
        """Create a new trip from a scanned boarding pass."""
        trip_id           = TripService.generate_trip_id()
        boarding_pass_id  = TripService._generate_boarding_pass_id()
        created_at        = datetime.utcnow()

        # Build segments (all outward by default for a new scan)
        trip_segments = TripService._create_segments_from_boarding_pass(
            boarding_pass, boarding_pass_id, journey_type="outward"
        )

        # Compute derived trip-level fields from outward segments
        derived = TripService._compute_derived_fields(trip_segments)

        # Build boarding pass attachment
        bp_attachment = {
            "boarding_pass_id":   boarding_pass_id,
            "boarding_pass_data": boarding_pass.model_dump(mode="json"),
            "segment_count":      len(boarding_pass.segments),
            "attached_at":        created_at.isoformat(),
            "extraction_metadata": {
                "overall_confidence": overall_confidence,
                "quality":            quality_label,
                "warnings":           [w.model_dump() for w in warnings],
                "method":             extraction_method,
                "engine_version":     "1.0.0",
                "extracted_at":       created_at.isoformat(),
            },
            "raw_ocr_text": raw_text,
        }

        passenger_name = (
            boarding_pass.passenger.full_name.value
            if boarding_pass.passenger.full_name else None
        )

        trip_data = {
            "trip_id":   trip_id,
            "user_id":   user_id,
            "tenant_id": tenant_id,
            "trip_type": "flight",
            "created_at": created_at,
            "updated_at": created_at,

            "segments":       trip_segments,
            "boarding_passes": [bp_attachment],

            "passenger_name": passenger_name,

            # Derived fields (computed from outward segments, stored for querying)
            **derived,

            "title":            TripService._generate_title(trip_segments),
            "description":      None,
            "notes":            None,
            "tags":             [],
            "user_corrections": [],

            "metadata": {
                "created_at": created_at.isoformat(),
                "updated_at": created_at.isoformat(),
                "source":     "boarding_pass_scan",
                "extraction_metadata": {
                    "overall_confidence": overall_confidence,
                    "quality":            quality_label,
                    "warnings":           [w.model_dump() for w in warnings],
                    "method":             extraction_method,
                    "engine_version":     "1.0.0",
                    "extracted_at":       created_at.isoformat(),
                },
            },
        }

        get_trip_ref(user_id, trip_id).set(trip_data)

        return {"trip_id": trip_id, "created_at": created_at.isoformat(), "data": trip_data}

    @staticmethod
    def create_manual_trip(
        user_id: str,
        tenant_id: str = "personal",
        trip_type: str = "flight",
        origin: Optional[str] = None,
        destination: Optional[str] = None,
        departure_date: Optional[str] = None,
        arrival_date: Optional[str] = None,
        airline_code: Optional[str] = None,
        flight_number: Optional[str] = None,
        passenger_name: Optional[str] = None,
        passenger_id: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a new trip manually (no boarding pass). Creates one outward segment."""
        trip_id    = TripService.generate_trip_id()
        created_at = datetime.utcnow()

        segment = {
            "segment_number":        1,
            "journey_type":          "outward",
            "origin":                origin,
            "destination":           destination,
            "departure_date":        departure_date,
            "departure_time":        None,
            "arrival_date":          arrival_date,
            "arrival_time":          None,
            "airline_code":          airline_code,
            "flight_number":         flight_number,
            "operating_carrier":     None,
            "seat":                  None,
            "gate":                  None,
            "boarding_time":         None,
            "boarding_pass_id":      None,
            "segment_index_in_pass": None,
            "passenger_id":          passenger_id,
            "manually_entered":      True,
            "notes":                 None,
        }
        TripService._enrich_segment(segment)

        segments = [segment]
        derived  = TripService._compute_derived_fields(segments)

        if not title:
            title = TripService._generate_title(segments) or f"{trip_type.capitalize()} Trip"

        trip_data = {
            "trip_id":   trip_id,
            "user_id":   user_id,
            "tenant_id": tenant_id,
            "trip_type": trip_type,
            "created_at": created_at,
            "updated_at": created_at,

            "segments":        segments,
            "boarding_passes": [],

            "passenger_name": passenger_name,

            # Derived fields
            **derived,

            "title":            title,
            "description":      description,
            "notes":            notes,
            "tags":             tags or [],
            "user_corrections": [],

            "metadata": {
                "created_at": created_at.isoformat(),
                "updated_at": created_at.isoformat(),
                "source":     "manual",
            },
        }

        get_trip_ref(user_id, trip_id).set(trip_data)

        return {"trip_id": trip_id, "created_at": created_at.isoformat(), "data": trip_data}

    @staticmethod
    def attach_boarding_pass_to_trip(
        user_id: str,
        trip_id: str,
        boarding_pass: BoardingPass,
        overall_confidence: float,
        quality_label: str,
        warnings: List[Warning],
        raw_text: str,
        journey_type: str = "outward",
        extraction_method: str = "rules"
    ) -> bool:
        """
        Attach a scanned boarding pass to an existing trip, adding new segments.
        Recomputes the trip-level derived fields after attaching.

        Args:
            journey_type: "outward" or "return" — how to classify the new segments
        """
        trip_ref  = get_trip_ref(user_id, trip_id)
        trip_doc  = trip_ref.get()
        if not trip_doc.exists:
            return False

        trip_data        = trip_doc.to_dict()
        boarding_pass_id = TripService._generate_boarding_pass_id()
        current_time     = datetime.utcnow()

        # Build new segments then insert each one in route order
        new_segments = TripService._create_segments_from_boarding_pass(
            boarding_pass, boarding_pass_id, journey_type=journey_type
        )
        all_segments = trip_data.get("segments", [])
        for seg in new_segments:
            all_segments = TripService._insert_segment_ordered(all_segments, seg)

        bp_attachment = {
            "boarding_pass_id":   boarding_pass_id,
            "boarding_pass_data": boarding_pass.model_dump(mode="json"),
            "segment_count":      len(boarding_pass.segments),
            "attached_at":        current_time.isoformat(),
            "extraction_metadata": {
                "overall_confidence": overall_confidence,
                "quality":            quality_label,
                "warnings":           [w.model_dump() for w in warnings],
                "method":             extraction_method,
                "engine_version":     "1.0.0",
                "extracted_at":       current_time.isoformat(),
            },
            "raw_ocr_text": raw_text,
        }

        # Recompute derived fields from updated outward segments
        derived = TripService._compute_derived_fields(all_segments)

        updates = {
            "segments":        all_segments,
            "boarding_passes": trip_data.get("boarding_passes", []) + [bp_attachment],
            "updated_at":      current_time,
            **derived,
        }

        trip_ref.update(updates)
        return True

    @staticmethod
    def add_manual_segment(
        user_id: str,
        trip_id: str,
        journey_type: str = "outward",
        origin: Optional[str] = None,
        destination: Optional[str] = None,
        departure_date: Optional[str] = None,
        departure_time: Optional[str] = None,
        arrival_date: Optional[str] = None,
        arrival_time: Optional[str] = None,
        airline_code: Optional[str] = None,
        flight_number: Optional[str] = None,
        seat: Optional[str] = None,
        gate: Optional[str] = None,
        boarding_time: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Add a manually entered segment to an existing trip.
        Inserts the segment in route order and recomputes derived fields.

        Returns a dict with the final segment_number, or None if trip not found.
        """
        trip_ref = get_trip_ref(user_id, trip_id)
        trip_doc = trip_ref.get()
        if not trip_doc.exists:
            return None

        trip_data    = trip_doc.to_dict()
        current_time = datetime.utcnow()

        new_segment = {
            "journey_type":          journey_type,
            "origin":                origin,
            "destination":           destination,
            "departure_date":        departure_date,
            "departure_time":        departure_time,
            "arrival_date":          arrival_date,
            "arrival_time":          arrival_time,
            "airline_code":          airline_code,
            "flight_number":         flight_number,
            "seat":                  seat,
            "gate":                  gate,
            "boarding_time":         boarding_time,
            "boarding_pass_id":      None,
            "segment_index_in_pass": None,
            "manually_entered":      True,
            "notes":                 notes,
            # segment_number will be assigned by _insert_segment_ordered
            "segment_number":        0,
        }
        TripService._enrich_segment(new_segment)

        all_segments = TripService._insert_segment_ordered(
            trip_data.get("segments", []), new_segment
        )
        derived = TripService._compute_derived_fields(all_segments)

        trip_ref.update({
            "segments":   all_segments,
            "updated_at": current_time,
            **derived,
        })

        # Return the assigned segment_number so the endpoint can report it
        assigned = next(s for s in all_segments if s is new_segment)
        return {"segment_number": assigned["segment_number"]}

    @staticmethod
    def update_manual_segment(
        user_id: str,
        trip_id: str,
        segment_number: int,
        **updates: Any,
    ) -> bool:
        """
        Update fields on an existing manually-entered segment.
        Recomputes derived trip-level fields if route or date fields change.

        Returns False if the trip or segment is not found, or if the segment
        was not manually entered.
        """
        trip_ref = get_trip_ref(user_id, trip_id)
        trip_doc = trip_ref.get()
        if not trip_doc.exists:
            return False

        trip_data = trip_doc.to_dict()
        segments  = trip_data.get("segments", [])

        # Find the target segment
        target = next((s for s in segments if s.get("segment_number") == segment_number), None)
        if target is None:
            return False

        # Apply updates to the segment in-place
        allowed = {
            "journey_type", "origin", "destination",
            "departure_date", "departure_time", "arrival_date", "arrival_time",
            "airline_code", "flight_number", "seat", "gate", "boarding_time", "notes",
            "passenger_id", "ticket_number", "aircraft",
            "departure_terminal", "arrival_terminal",
        }
        for key, value in updates.items():
            if key in allowed:
                target[key] = value

        # Re-enrich if route changed
        if "origin" in updates or "destination" in updates:
            TripService._enrich_segment(target)

        # Re-sort if journey_type changed (rare but safe to handle)
        derived = TripService._compute_derived_fields(segments)

        trip_ref.update({
            "segments":   segments,
            "updated_at": datetime.utcnow(),
            **derived,
        })
        return True

    @staticmethod
    def get_trip(user_id: str, trip_id: str) -> Optional[Dict[str, Any]]:
        trip_ref = get_trip_ref(user_id, trip_id)
        doc = trip_ref.get()
        return doc.to_dict() if doc.exists else None

    @staticmethod
    def list_trips(
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "created_at",
        order_direction: str = "desc"
    ) -> List[Dict[str, Any]]:
        trips_ref = get_user_trips_collection(user_id)
        direction = firestore.Query.DESCENDING if order_direction == "desc" else firestore.Query.ASCENDING
        docs = trips_ref.order_by(order_by, direction=direction).limit(limit).offset(offset).stream()
        return [doc.to_dict() for doc in docs]

    @staticmethod
    def search_trips(
        user_id: str,
        destination: Optional[str] = None,
        origin: Optional[str] = None,
        trip_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Search trips using trip-level derived fields (origin, destination, dates)."""
        trips_ref = get_user_trips_collection(user_id)
        query = trips_ref

        if trip_type:
            query = query.where("trip_type", "==", trip_type)
        if destination:
            query = query.where("destination", "==", destination)
        if origin:
            query = query.where("origin", "==", origin)
        if start_date:
            query = query.where("departure_date", ">=", start_date)
        if end_date:
            query = query.where("departure_date", "<=", end_date)

        return [doc.to_dict() for doc in query.limit(limit).stream()]

    @staticmethod
    def update_trip(user_id: str, trip_id: str, updates: Dict[str, Any]) -> bool:
        trip_ref = get_trip_ref(user_id, trip_id)
        if not trip_ref.get().exists:
            return False
        updates["updated_at"] = datetime.utcnow()
        trip_ref.update(updates)
        return True

    @staticmethod
    def delete_trip(user_id: str, trip_id: str) -> bool:
        trip_ref = get_trip_ref(user_id, trip_id)
        if not trip_ref.get().exists:
            return False
        trip_ref.delete()
        return True

    @staticmethod
    def get_trip_stats(user_id: str) -> Dict[str, Any]:
        trips = TripService.list_trips(user_id, limit=1000)

        if not trips:
            return {
                "total_trips": 0, "total_segments": 0, "total_flights": 0,
                "airlines": [], "destinations": [], "origins": [], "trip_types": {}
            }

        airlines, destinations, origins = set(), set(), set()
        trip_types: Dict[str, int] = {}
        total_segments = 0

        for trip in trips:
            trip_type = trip.get("trip_type", "other")
            trip_types[trip_type] = trip_types.get(trip_type, 0) + 1

            segments = trip.get("segments", [])
            total_segments += len(segments)

            # Aggregate unique values from segments (the source of truth)
            for seg in segments:
                if seg.get("airline_code"):
                    airlines.add(seg["airline_code"])
                if seg.get("destination"):
                    destinations.add(seg["destination"])
                if seg.get("origin"):
                    origins.add(seg["origin"])

        return {
            "total_trips":    len(trips),
            "total_segments": total_segments,
            "total_flights":  trip_types.get("flight", 0),
            "trip_types":     trip_types,
            "airlines":       sorted(airlines),
            "destinations":   sorted(destinations),
            "origins":        sorted(origins),
            "unique_routes":  len({
                f"{t.get('origin')}-{t.get('destination')}"
                for t in trips if t.get("origin") and t.get("destination")
            }),
        }

