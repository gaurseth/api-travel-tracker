# extractors/seat.py
import re
from models.common import ExtractedValue

SEAT_REGEX = re.compile(r"\b\d{1,2}[A-Z]\b")

def extract_seat(text: str, ocr_conf: float = 1.0) -> dict:
    seat_ev = None

    match = SEAT_REGEX.search(text)
    if match:
        seat_ev = ExtractedValue(
            value=match.group(0),
            confidence=round(0.9 * ocr_conf, 2)
        )

    return {
        "seat": seat_ev
    }
