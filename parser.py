# parser.py
from typing import Tuple, List
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
from scoring.aggregation import compute_overall_confidence, get_extraction_quality_label

def parse_boarding_pass(text: str) -> Tuple[BoardingPass, float, List[Warning], str]:
    """
    Parses boarding pass text and returns a structured BoardingPass object with confidence metrics.
    All fields use ExtractedValue with confidence scoring.

    Currently supports single-segment boarding passes (most common case).
    Multi-segment detection can be added in the future.

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
        barcode=None,  # barcode detection can be added later
        raw_ocr_text=text,
        segments=[segment]  # Single-segment array
    )

    # ---------- Compute Overall Confidence ----------
    overall_confidence, warnings = compute_overall_confidence(boarding_pass_obj)
    quality_label = get_extraction_quality_label(overall_confidence)

    return boarding_pass_obj, overall_confidence, warnings, quality_label
