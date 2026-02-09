# parser.py
from models.boarding_pass import BoardingPass, PassengerInfo, FlightInfo, BoardingInfo, RouteInfo, LocationInfo
from models.common import ExtractedValue
from extractors.flight_number import extract_flight_number
from extractors.passenger_name import extract_passenger_name
from extractors.seat import extract_seat
from extractors.route import extract_route
from extractors.date import extract_date
from extractors.boarding_time import extract_boarding_time
from extractors.pnr import extract_pnr, extract_ticket_number
from extractors.gate import extract_gate

def parse_boarding_pass(text: str):
    """
    Parses boarding pass text and returns a structured BoardingPass object.
    All fields use ExtractedValue with confidence scoring.
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

    # ---------- Date ----------
    date_info = extract_date(text, ocr_conf=1.0)

    flight_obj = FlightInfo(
        flight_number=flight_info["flightNumber"],
        airline_code=flight_info["airlineCode"],
        operating_carrier=None,  # can be enhanced later
        date=date_info["date_string"]
    )

    # ---------- Route ----------
    route_info = extract_route(text, ocr_conf=1.0)

    route_obj = None
    if route_info["origin"].value and route_info["destination"].value:
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

    # ---------- Build BoardingPass object ----------
    boarding_pass_obj = BoardingPass(
        passenger=passenger_obj,
        flight=flight_obj,
        airline=None,  # can be enhanced with airline lookup
        route=route_obj,
        boarding=boarding_obj,
        pnr=pnr if pnr.value else None,
        sequence_number=ticket_number if ticket_number.value else None,  # using ticket_number as sequence
        barcode=None,  # barcode detection can be added later
        raw_ocr_text=text
    )

    return boarding_pass_obj
