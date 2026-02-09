# parser.py
import re
from models.boarding_pass import BoardingPass, PassengerInfo, FlightInfo, BoardingInfo
from models.common import ExtractedValue
from extractors.flight_number import extract_flight_number
from extractors.passenger_name import extract_passenger_name
from extractors.seat import extract_seat

MONTHS = (
    "JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|"
    "JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER"
)

def parse_boarding_pass(text: str):
    data = {}
    confidence = {}

    # ---------- Passenger Name ----------
    passenger_info = extract_passenger_name(text, ocr_conf=1.0)
    passenger_obj = PassengerInfo(
        first_name=passenger_info["firstName"],
        last_name=passenger_info["lastName"],
        full_name=ExtractedValue(
            value=f"{passenger_info['firstName'].value} {passenger_info['lastName'].value}" 
                  if passenger_info["firstName"].value and passenger_info["lastName"].value else None,
            confidence=min(passenger_info["firstName"].confidence, passenger_info["lastName"].confidence),
            confidence_factors=None  # optional, can combine factors later
        )
    )

    # ---------- Flight Number ----------
    flight_info = extract_flight_number(text, ocr_conf=1.0)
    flight_obj = FlightInfo(
        flight_number=flight_info["flightNumber"],
        airline_code=flight_info["airlineCode"],
        operating_carrier=None,  # can be added later
        date=None  # placeholder, implement date extractor later
    )

    # ---------- Seat ----------
    seat_ev = extract_seat(text, ocr_conf=1.0)
    
    boarding_info = BoardingInfo(
        seat=seat_ev
        )

    # ---------- Route ----------
    route_match = re.search(r"\b([A-Z]{3})\s+TO\s+([A-Z]{3})\b", text)
    if route_match:
        data["from"] = route_match.group(1)
        data["to"] = route_match.group(2)
        confidence["route"] = 0.95
    else:
        confidence["route"] = 0.0

    # ---------- Date ----------
    date_match = re.search(
        rf"\b(\d{{1,2}})\s+({MONTHS})\b",
        text
    )
    if date_match:
        data["day"] = date_match.group(1)
        data["month"] = date_match.group(2).title()
        confidence["date"] = 0.85
    else:
        confidence["date"] = 0.0

    # ---------- Boarding Time ----------
    time_match = re.search(r"\b([01]?\d|2[0-3]):[0-5]\d\b", text)
    if time_match:
        data["boardingTime"] = time_match.group(0)
        confidence["boardingTime"] = 0.9
    else:
        confidence["boardingTime"] = 0.0

    # ---------- Ticket Number ----------
    ticket_match = re.search(r"\b(\d{3})\s?(\d{10})\b", text)
    if ticket_match:
        data["ticketNumber"] = f"{ticket_match.group(1)}{ticket_match.group(2)}"
        confidence["ticketNumber"] = 0.95
    else:
        confidence["ticketNumber"] = 0.0

    # ---------- Overall Confidence ----------
    valid_scores = [v for v in confidence.values() if v > 0]
    overall_confidence = round(
        sum(valid_scores) / len(valid_scores), 2
    ) if valid_scores else 0.0

    #return {
    #    "data": data,
    #    "confidence": confidence,
    #    "overallConfidence": overall_confidence
    #}

    # ---------- Build BoardingPass object ----------
    boarding_pass_obj = BoardingPass(
        passenger=passenger_obj,
        flight=flight_obj,
        airline=None,         # placeholder
        route=None,           # placeholder
        boarding=boarding_info,
        pnr=None,             # placeholder
        sequence_number=None, # placeholder
        barcode=None,         # placeholder
        raw_ocr_text=text     # store the raw text
    )

    return boarding_pass_obj
