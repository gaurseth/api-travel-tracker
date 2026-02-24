"""
Trip service for managing trips in Firestore with multi-segment support.
Supports creating trips with or without boarding passes, and multiple segments per trip.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
from google.cloud import firestore

from models.boarding_pass import BoardingPass
from models.trip_segment import TripSegment
from models.boarding_pass_attachment import BoardingPassAttachment
from models.common import Warning
from database import get_user_trips_collection, get_trip_ref


class TripService:
    """Service for managing trips in Firestore with multi-segment support."""

    @staticmethod
    def generate_trip_id() -> str:
        """Generate a unique trip ID."""
        return f"trip_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _generate_boarding_pass_id() -> str:
        """Generate a unique boarding pass ID."""
        return f"bp_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _create_segments_from_boarding_pass(
        boarding_pass: BoardingPass,
        boarding_pass_id: str
    ) -> List[Dict[str, Any]]:
        """
        Convert boarding pass segments to trip segments.

        Args:
            boarding_pass: Boarding pass object with segments
            boarding_pass_id: ID to reference this boarding pass

        Returns:
            List of trip segment dictionaries
        """
        trip_segments = []

        for bp_segment in boarding_pass.segments:
            trip_segment = {
                "segment_number": bp_segment.segment_number,

                # Route
                "origin": bp_segment.route.origin.iata.value if bp_segment.route.origin.iata.value else None,
                "destination": bp_segment.route.destination.iata.value if bp_segment.route.destination.iata.value else None,

                # Schedule
                "departure_date": bp_segment.schedule.departure_date.value if bp_segment.schedule and bp_segment.schedule.departure_date else None,
                "departure_time": bp_segment.schedule.departure_time.value if bp_segment.schedule and bp_segment.schedule.departure_time else None,
                "arrival_date": bp_segment.schedule.arrival_date.value if bp_segment.schedule and bp_segment.schedule.arrival_date else None,
                "arrival_time": bp_segment.schedule.arrival_time.value if bp_segment.schedule and bp_segment.schedule.arrival_time else None,

                # Flight info
                "airline_code": bp_segment.flight.airline_code.value if bp_segment.flight.airline_code.value else None,
                "flight_number": bp_segment.flight.flight_number.value if bp_segment.flight.flight_number.value else None,
                "operating_carrier": None,

                # Boarding info
                "seat": bp_segment.boarding.seat.value if bp_segment.boarding and bp_segment.boarding.seat else None,
                "gate": bp_segment.boarding.gate.value if bp_segment.boarding and bp_segment.boarding.gate else None,
                "boarding_time": bp_segment.boarding.time.value if bp_segment.boarding and bp_segment.boarding.time else None,

                # Reference
                "boarding_pass_id": boarding_pass_id,
                "segment_index_in_pass": bp_segment.segment_number - 1,  # 0-indexed

                # Metadata
                "manually_entered": False,
                "notes": None
            }
            trip_segments.append(trip_segment)

        return trip_segments

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
        """
        Create a new trip from a scanned boarding pass (supports multi-segment passes).

        Args:
            user_id: User identifier
            tenant_id: Tenant identifier
            boarding_pass: Parsed boarding pass object (may have multiple segments)
            overall_confidence: Overall extraction confidence
            quality_label: Quality label (excellent, good, medium, low)
            warnings: List of extraction warnings
            raw_text: Raw OCR text
            extraction_method: Extraction method used

        Returns:
            Dict containing trip_id and created document data
        """
        trip_id = TripService.generate_trip_id()
        boarding_pass_id = TripService._generate_boarding_pass_id()
        created_at = datetime.utcnow()

        # Create trip segments from boarding pass segments
        trip_segments = TripService._create_segments_from_boarding_pass(
            boarding_pass, boarding_pass_id
        )

        # Create boarding pass attachment
        boarding_pass_attachment = {
            "boarding_pass_id": boarding_pass_id,
            "boarding_pass_data": boarding_pass.model_dump(mode='json'),
            "segment_count": len(boarding_pass.segments),
            "attached_at": created_at.isoformat(),
            "extraction_metadata": {
                "overall_confidence": overall_confidence,
                "quality": quality_label,
                "warnings": [w.model_dump() for w in warnings],
                "method": extraction_method,
                "engine_version": "1.0.0",
                "extracted_at": created_at.isoformat()
            },
            "raw_ocr_text": raw_text
        }

        # Extract passenger name (common across all segments)
        passenger_name = boarding_pass.passenger.full_name.value if boarding_pass.passenger.full_name else None

        # Legacy fields (populated from first segment for backward compatibility)
        first_segment = trip_segments[0] if trip_segments else {}
        origin = first_segment.get("origin")
        destination = trip_segments[-1].get("destination") if trip_segments else None  # Last segment's destination
        departure_date = first_segment.get("departure_date")
        arrival_date = trip_segments[-1].get("arrival_date") if trip_segments else None
        airline_code = first_segment.get("airline_code")
        flight_number = first_segment.get("flight_number")

        # Auto-generate title
        if len(trip_segments) > 1:
            # Multi-segment: "DXB → DOH → JFK"
            route_str = " → ".join([seg.get("origin", "?") for seg in trip_segments] + [trip_segments[-1].get("destination", "?")])
            title = route_str
        else:
            # Single segment
            title = f"{origin} → {destination}" if origin and destination else "Flight"

        if flight_number and len(trip_segments) == 1:
            title = f"{airline_code}{flight_number}: {title}"

        trip_data = {
            "trip_id": trip_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "trip_type": "flight",
            "created_at": created_at,
            "updated_at": created_at,

            # Multi-segment architecture (PRIMARY)
            "segments": trip_segments,
            "boarding_passes": [boarding_pass_attachment],

            # Legacy fields (for backward compatibility)
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "arrival_date": arrival_date,
            "airline_code": airline_code,
            "flight_number": flight_number,
            "passenger_name": passenger_name,
            "raw_ocr_text": raw_text,

            # User fields
            "title": title,
            "description": None,
            "notes": None,
            "tags": [],
            "user_corrections": [],

            # Metadata
            "metadata": {
                "created_at": created_at.isoformat(),
                "updated_at": created_at.isoformat(),
                "source": "boarding_pass_scan",
                "extraction_metadata": {
                    "overall_confidence": overall_confidence,
                    "quality": quality_label,
                    "warnings": [w.model_dump() for w in warnings],
                    "method": extraction_method,
                    "engine_version": "1.0.0",
                    "extracted_at": created_at.isoformat()
                }
            }
        }

        # Save to Firestore
        trip_ref = get_trip_ref(user_id, trip_id)
        trip_ref.set(trip_data)

        return {
            "trip_id": trip_id,
            "created_at": created_at.isoformat(),
            "data": trip_data
        }

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
        """
        Create a new trip manually (without boarding pass).
        Creates a single-segment trip.

        Args:
            user_id: User identifier
            tenant_id: Tenant identifier
            trip_type: Type of trip (flight, train, bus, car, hotel, other)
            origin: Origin location
            destination: Destination location
            departure_date: Departure date (ISO-8601)
            arrival_date: Arrival date (ISO-8601)
            airline_code: Airline code (for flights)
            flight_number: Flight number (for flights)
            passenger_name: Passenger name
            title: Trip title
            description: Trip description
            notes: User notes
            tags: List of tags

        Returns:
            Dict containing trip_id and created document data
        """
        trip_id = TripService.generate_trip_id()
        created_at = datetime.utcnow()

        # Create a single trip segment
        segment = {
            "segment_number": 1,
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "departure_time": None,
            "arrival_date": arrival_date,
            "arrival_time": None,
            "airline_code": airline_code,
            "flight_number": flight_number,
            "operating_carrier": None,
            "seat": None,
            "gate": None,
            "boarding_time": None,
            "boarding_pass_id": None,  # No boarding pass
            "segment_index_in_pass": None,
            "manually_entered": True,
            "notes": notes
        }

        # Auto-generate title if not provided
        if not title:
            if origin and destination:
                title = f"{origin} → {destination}"
            else:
                title = f"{trip_type.capitalize()} Trip"

        trip_data = {
            "trip_id": trip_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "trip_type": trip_type,
            "created_at": created_at,
            "updated_at": created_at,

            # Multi-segment architecture
            "segments": [segment],
            "boarding_passes": [],  # No boarding passes

            # Legacy fields (for backward compatibility)
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "arrival_date": arrival_date,
            "airline_code": airline_code,
            "flight_number": flight_number,
            "passenger_name": passenger_name,
            "raw_ocr_text": None,

            # User fields
            "title": title,
            "description": description,
            "notes": notes,
            "tags": tags or [],
            "user_corrections": [],

            # Metadata
            "metadata": {
                "created_at": created_at.isoformat(),
                "updated_at": created_at.isoformat(),
                "source": "manual"
            }
        }

        # Save to Firestore
        trip_ref = get_trip_ref(user_id, trip_id)
        trip_ref.set(trip_data)

        return {
            "trip_id": trip_id,
            "created_at": created_at.isoformat(),
            "data": trip_data
        }

    @staticmethod
    def attach_boarding_pass_to_trip(
        user_id: str,
        trip_id: str,
        boarding_pass: BoardingPass,
        overall_confidence: float,
        quality_label: str,
        warnings: List[Warning],
        raw_text: str,
        extraction_method: str = "rules"
    ) -> bool:
        """
        Attach a scanned boarding pass to an existing trip.
        Adds new segments from the boarding pass and stores the boarding pass data.

        Args:
            user_id: User identifier
            trip_id: Trip identifier
            boarding_pass: Parsed boarding pass object
            overall_confidence: Overall extraction confidence
            quality_label: Quality label
            warnings: List of extraction warnings
            raw_text: Raw OCR text
            extraction_method: Extraction method used

        Returns:
            True if successful, False if trip not found
        """
        trip_ref = get_trip_ref(user_id, trip_id)

        # Check if trip exists
        trip_doc = trip_ref.get()
        if not trip_doc.exists:
            return False

        trip_data = trip_doc.to_dict()
        boarding_pass_id = TripService._generate_boarding_pass_id()
        current_time = datetime.utcnow()

        # Create new segments from boarding pass
        new_segments = TripService._create_segments_from_boarding_pass(
            boarding_pass, boarding_pass_id
        )

        # Update segment numbers (continue from existing segments)
        existing_segments = trip_data.get("segments", [])
        next_segment_number = len(existing_segments) + 1
        for seg in new_segments:
            seg["segment_number"] = next_segment_number
            next_segment_number += 1

        # Create boarding pass attachment
        boarding_pass_attachment = {
            "boarding_pass_id": boarding_pass_id,
            "boarding_pass_data": boarding_pass.model_dump(mode='json'),
            "segment_count": len(boarding_pass.segments),
            "attached_at": current_time.isoformat(),
            "extraction_metadata": {
                "overall_confidence": overall_confidence,
                "quality": quality_label,
                "warnings": [w.model_dump() for w in warnings],
                "method": extraction_method,
                "engine_version": "1.0.0",
                "extracted_at": current_time.isoformat()
            },
            "raw_ocr_text": raw_text
        }

        # Update trip
        existing_boarding_passes = trip_data.get("boarding_passes", [])
        updates = {
            "segments": existing_segments + new_segments,
            "boarding_passes": existing_boarding_passes + [boarding_pass_attachment],
            "updated_at": current_time
        }

        trip_ref.update(updates)
        return True

    @staticmethod
    def get_trip(user_id: str, trip_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific trip by ID.

        Args:
            user_id: User identifier
            trip_id: Trip identifier

        Returns:
            Trip document data or None if not found
        """
        trip_ref = get_trip_ref(user_id, trip_id)
        doc = trip_ref.get()

        if doc.exists:
            return doc.to_dict()
        return None

    @staticmethod
    def list_trips(
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "created_at",
        order_direction: str = "desc"
    ) -> List[Dict[str, Any]]:
        """
        List all trips for a user with pagination.

        Args:
            user_id: User identifier
            limit: Maximum number of results
            offset: Number of results to skip
            order_by: Field to order by
            order_direction: 'asc' or 'desc'

        Returns:
            List of trip documents
        """
        trips_ref = get_user_trips_collection(user_id)

        # Build query
        direction = firestore.Query.DESCENDING if order_direction == "desc" else firestore.Query.ASCENDING
        query = trips_ref.order_by(order_by, direction=direction).limit(limit).offset(offset)

        # Execute query
        docs = query.stream()

        return [doc.to_dict() for doc in docs]

    @staticmethod
    def search_trips(
        user_id: str,
        destination: Optional[str] = None,
        origin: Optional[str] = None,
        airline: Optional[str] = None,
        trip_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Search trips with filters.

        Args:
            user_id: User identifier
            destination: Filter by destination
            origin: Filter by origin
            airline: Filter by airline code
            trip_type: Filter by trip type
            start_date: Filter by departure_date >= start_date
            end_date: Filter by departure_date <= end_date
            limit: Maximum number of results

        Returns:
            List of matching trip documents
        """
        trips_ref = get_user_trips_collection(user_id)
        query = trips_ref

        # Apply filters
        if trip_type:
            query = query.where("trip_type", "==", trip_type)
        if destination:
            query = query.where("destination", "==", destination)
        if origin:
            query = query.where("origin", "==", origin)
        if airline:
            query = query.where("airline_code", "==", airline)
        if start_date:
            query = query.where("departure_date", ">=", start_date)
        if end_date:
            query = query.where("departure_date", "<=", end_date)

        # Note: Firestore has limitations on compound queries
        # You may need to create composite indexes for complex queries

        query = query.limit(limit)
        docs = query.stream()

        return [doc.to_dict() for doc in docs]

    @staticmethod
    def update_trip(
        user_id: str,
        trip_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update a trip document.

        Args:
            user_id: User identifier
            trip_id: Trip identifier
            updates: Dictionary of fields to update

        Returns:
            True if update successful, False if trip not found
        """
        trip_ref = get_trip_ref(user_id, trip_id)

        # Check if document exists
        if not trip_ref.get().exists:
            return False

        # Add updated_at timestamp
        updates["updated_at"] = datetime.utcnow()

        trip_ref.update(updates)
        return True

    @staticmethod
    def delete_trip(user_id: str, trip_id: str) -> bool:
        """
        Delete a trip document.

        Args:
            user_id: User identifier
            trip_id: Trip identifier

        Returns:
            True if deletion successful, False if trip not found
        """
        trip_ref = get_trip_ref(user_id, trip_id)

        # Check if document exists
        if not trip_ref.get().exists:
            return False

        trip_ref.delete()
        return True

    @staticmethod
    def get_trip_stats(user_id: str) -> Dict[str, Any]:
        """
        Get statistics about user's trips.

        Args:
            user_id: User identifier

        Returns:
            Dictionary with trip statistics
        """
        trips = TripService.list_trips(user_id, limit=1000)  # Get all trips

        if not trips:
            return {
                "total_trips": 0,
                "total_segments": 0,
                "total_flights": 0,
                "airlines": [],
                "destinations": [],
                "origins": [],
                "trip_types": {}
            }

        airlines = set()
        destinations = set()
        origins = set()
        trip_types = {}
        total_segments = 0

        for trip in trips:
            # Count trip types
            trip_type = trip.get("trip_type", "other")
            trip_types[trip_type] = trip_types.get(trip_type, 0) + 1

            # Count segments
            segments = trip.get("segments", [])
            total_segments += len(segments)

            # Collect unique values from segments
            for segment in segments:
                if segment.get("airline_code"):
                    airlines.add(segment["airline_code"])
                if segment.get("destination"):
                    destinations.add(segment["destination"])
                if segment.get("origin"):
                    origins.add(segment["origin"])

            # Also collect from legacy fields (backward compatibility)
            if trip.get("airline_code"):
                airlines.add(trip["airline_code"])
            if trip.get("destination"):
                destinations.add(trip["destination"])
            if trip.get("origin"):
                origins.add(trip["origin"])

        return {
            "total_trips": len(trips),
            "total_segments": total_segments,
            "total_flights": trip_types.get("flight", 0),
            "trip_types": trip_types,
            "airlines": list(airlines),
            "destinations": list(destinations),
            "origins": list(origins),
            "unique_routes": len(set(f"{t.get('origin')}-{t.get('destination')}" for t in trips if t.get('origin') and t.get('destination')))
        }
