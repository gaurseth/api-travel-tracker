import re
from models.common import ExtractedValue, ConfidenceFactors
from scoring.confidence import compute_confidence

def extract_route(text: str, ocr_conf: float = 1.0):
    """
    Extracts origin and destination airport codes.
    Returns a dict with:
    {
        "origin": ExtractedValue(...),
        "destination": ExtractedValue(...)
    }
    """
    route_match = re.search(r"\b([A-Z]{3})\s+TO\s+([A-Z]{3})\b", text)

    if not route_match:
        return {
            "origin": ExtractedValue(value=None, confidence=0.0, confidence_factors=None),
            "destination": ExtractedValue(value=None, confidence=0.0, confidence_factors=None)
        }

    factors = ConfidenceFactors(
        ocr=ocr_conf,
        pattern=1.0,  # Strong pattern match with "TO" keyword
        context=0.95,  # "TO" provides strong context
        airline=0.8    # Airport codes are standardized
    )

    confidence_score = compute_confidence(factors)

    return {
        "origin": ExtractedValue(
            value=route_match.group(1),
            confidence=confidence_score,
            confidence_factors=factors
        ),
        "destination": ExtractedValue(
            value=route_match.group(2),
            confidence=confidence_score,
            confidence_factors=factors
        )
    }
