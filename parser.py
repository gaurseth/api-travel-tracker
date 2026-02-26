# parser.py
from typing import Tuple, List, Optional
from models.boarding_pass import (
    BoardingPass, PassengerInfo, FlightInfo, BoardingInfo,
    RouteInfo, LocationInfo, ScheduleInfo, FlightSegment
)
from models.common import ExtractedValue, Warning
from extractors.flight_number import extract_flight_number
from extractors.passenger_name import extract_passenger_name
from extractors.seat import extract_seat
from extractors.route import extract_route
from extractors.date import extract_date
from extractors.boarding_time import extract_boarding_time
from extractors.pnr import extract_pnr, extract_ticket_number
from extractors.gate import extract_gate
from extractors.bcbp_extractor import BCBPParser
from scoring.aggregation import compute_overall_confidence, get_extraction_quality_label


def parse_boarding_pass(text: str) -> Tuple[BoardingPass, float, List[Warning], str]:
    """
    Parse a boarding pass from OCR text.

    Args:
        text: OCR text extracted from boarding pass image

    Returns:
        Tuple of (boarding_pass, overall_confidence, warnings, quality_label)
    """
    print("📄 Using OCR-based extraction...")
    return _parse_boarding_pass_from_ocr(text)


def parse_boarding_pass_from_bcbp(
    bcbp_string: str,
    ocr_text: str = ""
) -> Tuple[BoardingPass, float, List[Warning], str]:
    """
    Parse a boarding pass from a raw BCBP string (scanned by the frontend).

    Args:
        bcbp_string: Raw IATA BCBP string from a PDF417 barcode scan
        ocr_text: Optional OCR text to store alongside (default empty)

    Returns:
        Tuple of (boarding_pass, overall_confidence, warnings, quality_label)

    Raises:
        ValueError: If the BCBP string is invalid or cannot be parsed
    """
    bcbp_data = BCBPParser.parse(bcbp_string)
    if not bcbp_data:
        raise ValueError("Invalid or unrecognised BCBP string. Must start with 'M' and contain at least one segment.")

    boarding_pass = _create_boarding_pass_from_bcbp(bcbp_data, ocr_text)
    return boarding_pass, 0.98, [], "excellent"


def _create_boarding_pass_from_bcbp(bcbp_data: dict, ocr_text: str) -> BoardingPass:
    """
    Create BoardingPass object from barcode (BCBP) data.

    Args:
        bcbp_data: Parsed BCBP data from barcode
        ocr_text: Original OCR text (stored for reference)

    Returns:
        BoardingPass object with data from barcode
    """
    # ---------- Passenger Info (from barcode) ----------
    passenger_first = bcbp_data.get("passenger_first_name", "")
    passenger_last = bcbp_data.get("passenger_last_name", "")
    passenger_full = bcbp_data.get("passenger_name", f"{passenger_last} {passenger_first}".strip())

    passenger_obj = PassengerInfo(
        first_name=ExtractedValue(value=passenger_first, confidence=1.0) if passenger_first else None,
        last_name=ExtractedValue(value=passenger_last, confidence=1.0) if passenger_last else None,
        full_name=ExtractedValue(value=passenger_full, confidence=1.0)
    )

    # ---------- PNR (from barcode) ----------
    pnr_value = bcbp_data.get("pnr")
    pnr = ExtractedValue(value=pnr_value, confidence=1.0) if pnr_value else None

    # ---------- Create segments from barcode data ----------
    segments = []
    bcbp_segments = bcbp_data.get("segments", [])

    for bcbp_seg in bcbp_segments:
        # Flight info
        flight_obj = FlightInfo(
            flight_number=ExtractedValue(value=bcbp_seg.get("flight_number"), confidence=1.0),
            airline_code=ExtractedValue(value=bcbp_seg.get("airline_code"), confidence=1.0),
            operating_carrier=None
        )

        # Route info
        route_obj = RouteInfo(
            origin=LocationInfo(
                iata=ExtractedValue(value=bcbp_seg.get("origin"), confidence=1.0),
                city=None
            ),
            destination=LocationInfo(
                iata=ExtractedValue(value=bcbp_seg.get("destination"), confidence=1.0),
                city=None
            )
        )

        # Schedule info
        schedule_obj = ScheduleInfo(
            departure_date=ExtractedValue(value=bcbp_seg.get("departure_date"), confidence=1.0),
            departure_time=None,  # Not in barcode
            arrival_date=None,  # Not in barcode
            arrival_time=None  # Not in barcode
        )

        # Boarding info
        seat_value = bcbp_seg.get("seat")
        boarding_obj = BoardingInfo(
            time=None,  # Not in barcode
            gate=None,  # Not in barcode
            seat=ExtractedValue(value=seat_value, confidence=1.0) if seat_value else None,
            group=None
        )

        # Create segment
        segment = FlightSegment(
            segment_number=bcbp_seg.get("segment_number", 1),
            flight=flight_obj,
            route=route_obj,
            schedule=schedule_obj,
            boarding=boarding_obj,
            sequence_number=ExtractedValue(value=bcbp_seg.get("checkin_sequence"), confidence=1.0)
            if bcbp_seg.get("checkin_sequence") else None
        )

        segments.append(segment)

    # ---------- Build BoardingPass object ----------
    boarding_pass_obj = BoardingPass(
        passenger=passenger_obj,
        airline=None,  # Could be enhanced with airline lookup
        pnr=pnr,
        barcode={
            "present": True,
            "type": "PDF417",
            "confidence": 1.0
        },
        raw_ocr_text=ocr_text,
        segments=segments
    )

    return boarding_pass_obj


def _parse_boarding_pass_from_ocr(text: str) -> Tuple[BoardingPass, float, List[Warning], str]:
    """
    Parse boarding pass using OCR-based rule extraction (fallback method).

    This is the original extraction logic using regex patterns.

    Args:
        text: OCR text from boarding pass

    Returns:
        Tuple of (boarding_pass, overall_confidence, warnings, quality_label)
    """
    # ---------- Passenger Name ----------
    passenger_info = extract_passenger_name(text, ocr_conf=1.0)
    passenger_obj = PassengerInfo(
        first_name=passenger_info["firstName"],
        last_name=passenger_info["lastName"],
        full_name=ExtractedValue(
            value=f"{passenger_info['firstName'].value} {passenger_info['lastName'].value}"
                  if passenger_info["firstName"].value and passenger_info["lastName"].value else None,
            confidence=min(passenger_info["firstName"].confidence, passenger_info["lastName"].confidence)
                       if passenger_info["firstName"].value and passenger_info["lastName"].value else 0.0,
            confidence_factors=None
        )
    )

    # ---------- Flight Number & Airline ----------
    flight_info = extract_flight_number(text, ocr_conf=1.0)

    flight_obj = FlightInfo(
        flight_number=flight_info["flightNumber"],
        airline_code=flight_info["airlineCode"],
        operating_carrier=None  # can be enhanced later
    )

    # ---------- Route ----------
    route_info = extract_route(text, ocr_conf=1.0)

    route_obj = RouteInfo(
        origin=LocationInfo(
            iata=route_info["origin"],
            city=None  # can be enriched with airport lookup later
        ),
        destination=LocationInfo(
            iata=route_info["destination"],
            city=None
        )
    )

    # ---------- Schedule Info (dates and times) ----------
    date_info = extract_date(text, ocr_conf=1.0)

    schedule_obj = ScheduleInfo(
        departure_date=date_info["date_string"],
        departure_time=None,  # TODO: Add departure_time extractor
        arrival_date=None,  # TODO: Add arrival_date extractor
        arrival_time=None  # TODO: Add arrival_time extractor
    )

    # ---------- Boarding Info ----------
    seat_result = extract_seat(text, ocr_conf=1.0)
    boarding_time = extract_boarding_time(text, ocr_conf=1.0)
    gate = extract_gate(text, ocr_conf=1.0)

    boarding_obj = BoardingInfo(
        time=boarding_time,
        gate=gate,
        seat=seat_result["seat"],
        group=None  # can be added later
    )

    # ---------- PNR & Ticket Number ----------
    pnr = extract_pnr(text, ocr_conf=1.0)
    ticket_number = extract_ticket_number(text, ocr_conf=1.0)

    # ---------- Build Flight Segment ----------
    segment = FlightSegment(
        segment_number=1,  # Single segment for now
        flight=flight_obj,
        route=route_obj,
        schedule=schedule_obj,
        boarding=boarding_obj,
        sequence_number=ticket_number if ticket_number.value else None
    )

    # ---------- Build BoardingPass object ----------
    boarding_pass_obj = BoardingPass(
        passenger=passenger_obj,
        airline=None,  # can be enhanced with airline lookup
        pnr=pnr if pnr.value else None,
        barcode=None,  # No barcode detected
        raw_ocr_text=text,
        segments=[segment]  # Single-segment array
    )

    # ---------- Compute Overall Confidence ----------
    overall_confidence, warnings = compute_overall_confidence(boarding_pass_obj)
    quality_label = get_extraction_quality_label(overall_confidence)

    return boarding_pass_obj, overall_confidence, warnings, quality_label
