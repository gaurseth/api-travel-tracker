import re
from models.common import ExtractedValue, ConfidenceFactors
from scoring.confidence import compute_confidence

def extract_boarding_time(text: str, ocr_conf: float = 1.0):
    """
    Extracts boarding time in HH:MM format.
    Returns ExtractedValue object.
    """
    # Look for time pattern, optionally with BOARDING or BOARD keyword nearby
    time_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)

    if not time_match:
        return ExtractedValue(value=None, confidence=0.0, confidence_factors=None)

    time_value = time_match.group(0)

    # Check if "BOARDING" or "BOARD" appears near the time for context boost
    context_window = text[max(0, time_match.start()-30):min(len(text), time_match.end()+30)]
    has_boarding_context = bool(re.search(r"\b(BOARDING|BOARD|BRD)\b", context_window, re.IGNORECASE))

    factors = ConfidenceFactors(
        ocr=ocr_conf,
        pattern=0.95,  # Time pattern is fairly strong
        context=0.9 if has_boarding_context else 0.7,  # Higher if "BOARDING" nearby
        airline=0.85   # Time format is standard
    )

    confidence_score = compute_confidence(factors)

    return ExtractedValue(
        value=time_value,
        confidence=confidence_score,
        confidence_factors=factors
    )
