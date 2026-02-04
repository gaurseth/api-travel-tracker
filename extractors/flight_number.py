import re
from models.common import ExtractedValue, ConfidenceFactors
from scoring.confidence import compute_confidence

def extract_flight_number(text: str, ocr_conf: float = 1.0):
    """
    Extracts airline code and flight number separately.
    Returns a dict of ExtractedValue objects:
    {
        "airlineCode": ExtractedValue(...),
        "flightNumber": ExtractedValue(...)
    }
    """
    match = re.search(r"\b([A-Z]{2})\s?(\d{2,4})\b", text)
    
    if not match:
        return {
            "airlineCode": ExtractedValue(value=None, confidence=0.0, confidence_factors=None),
            "flightNumber": ExtractedValue(value=None, confidence=0.0, confidence_factors=None)
        }

    factors = ConfidenceFactors(
        ocr=ocr_conf,
        pattern=1.0,
        context=0.8,
        airline=1.0
    )

    confidence_score = compute_confidence(factors)

    return {
        "airlineCode": ExtractedValue(
            value=match.group(1),
            confidence=confidence_score,
            confidence_factors=factors
        ),
        "flightNumber": ExtractedValue(
            value=match.group(2),
            confidence=confidence_score,
            confidence_factors=factors
        )
    }
