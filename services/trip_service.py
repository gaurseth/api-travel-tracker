"""
Trip service for managing trips in Firestore with multi-segment support.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
from google.cloud import firestore

from models.boarding_pass import BoardingPass
from models.common import Warning
from database import get_user_trips_collection, get_trip_ref


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
        stops = [outward[0].get("origin", "?")] + \
                [s.get("destination", "?") for s in outward]
        title = " → ".join(stops)

        # Prefix with flight number for single-leg trips
        if len(outward) == 1:
            airline = outward[0].get("airline_code", "")
            flight  = outward[0].get("flight_number", "")
            if airline and flight:
                title = f"{airline}{flight}: {title}"

        return title

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

                # Metadata
                "manually_entered": False,
                "notes":            None,
            }
            trip_segments.append(trip_segment)

        return trip_segments

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
            "manually_entered":      True,
            "notes":                 None,
        }

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

        # Build new segments, continuing the segment_number sequence
        new_segments = TripService._create_segments_from_boarding_pass(
            boarding_pass, boarding_pass_id, journey_type=journey_type
        )
        existing_segments = trip_data.get("segments", [])
        next_num = len(existing_segments) + 1
        for seg in new_segments:
            seg["segment_number"] = next_num
            next_num += 1

        all_segments = existing_segments + new_segments

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
