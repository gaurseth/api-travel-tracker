# extractors/seat.py
import re
from models.common import ExtractedValue, ConfidenceFactors
from scoring.confidence import compute_confidence

SEAT_REGEX = re.compile(r"\b\d{1,2}[A-Z]\b")

def extract_seat(text: str, ocr_conf: float = 1.0) -> dict:
    """
    Extracts seat number (e.g., 22A, 5B).
    Returns dict with ExtractedValue object.
    """
    match = SEAT_REGEX.search(text)

    if not match:
        return {
            "seat": ExtractedValue(value=None, confidence=0.0, confidence_factors=None)
        }

    # Check for "SEAT" keyword nearby for context boost
    context_window = text[max(0, match.start()-20):min(len(text), match.end()+20)]
    has_seat_context = bool(re.search(r"\b(SEAT|SIT|ASIENTO)\b", context_window, re.IGNORECASE))

    factors = ConfidenceFactors(
        ocr=ocr_conf,
        pattern=0.95,  # Strong pattern
        context=0.9 if has_seat_context else 0.75,
        airline=0.9    # Seat format is standardized
    )

    confidence_score = compute_confidence(factors)

    return {
        "seat": ExtractedValue(
            value=match.group(0),
            confidence=confidence_score,
            confidence_factors=factors
        )
    }
