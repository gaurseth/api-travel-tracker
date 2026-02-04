# parser.py
import re
from extractors.flight_number import extract_flight_number

MONTHS = (
    "JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|"
    "JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER"
)

def parse_boarding_pass(text: str):
    data = {}
    confidence = {}

    # ---------- Passenger Name ----------
    name_match = re.search(
        r"\b([A-Z]+)\/([A-Z]+)\s+(MR|MRS|MS|MISS|DR)\b",
        text
    )
    if name_match:
        data["lastName"] = name_match.group(1)
        data["firstName"] = name_match.group(2)
        data["title"] = name_match.group(3)
        confidence["passengerName"] = 0.95
    else:
        confidence["passengerName"] = 0.0

    # ---------- Flight Number ----------
    flight_info = extract_flight_number(text, ocr_conf=1.0)
    data["airlineCode"] = flight_info["airlineCode"].value
    confidence["airlineCode"] = flight_info["airlineCode"].confidence

    data["flightNumber"] = flight_info["flightNumber"].value
    confidence["flightNumber"] = flight_info["flightNumber"].confidence

    # ---------- Seat ----------
    seat_match = re.search(r"\b\d{1,2}[A-Z]\b", text)
    if seat_match:
        data["seat"] = seat_match.group(0)
        confidence["seat"] = 0.9
    else:
        confidence["seat"] = 0.0

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

    return {
        "data": data,
        "confidence": confidence,
        "overallConfidence": overall_confidence
    }
