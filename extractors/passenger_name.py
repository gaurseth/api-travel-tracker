import re
from models.common import ExtractedValue, ConfidenceFactors
from scoring.confidence import compute_confidence

def extract_passenger_name(text: str, ocr_conf: float = 1.0):
    """
    Extracts passenger name: last name, first name, title
    Returns a dict of ExtractedValue objects:
    {
        "lastName": ExtractedValue(...),
        "firstName": ExtractedValue(...),
        "title": ExtractedValue(...)
    }
    """
    name_match = re.search(
        r"\b([A-Z]+)\/([A-Z]+)\s+(MR|MRS|MS|MISS|DR)\b",
        text
    )

    if not name_match:
        return {
            "lastName": ExtractedValue(value=None, confidence=0.0, confidence_factors=None),
            "firstName": ExtractedValue(value=None, confidence=0.0, confidence_factors=None),
            "title": ExtractedValue(value=None, confidence=0.0, confidence_factors=None),
        }

    factors = ConfidenceFactors(
        ocr=ocr_conf,
        pattern=1.0,
        context=0.9,   # slightly higher context since format is usually standardized
        airline=0.0    # airline factor not relevant here
    )

    confidence_score = compute_confidence(factors)

    return {
        "lastName": ExtractedValue(
            value=name_match.group(1),
            confidence=confidence_score,
            confidence_factors=factors
        ),
        "firstName": ExtractedValue(
            value=name_match.group(2),
            confidence=confidence_score,
            confidence_factors=factors
        ),
        "title": ExtractedValue(
            value=name_match.group(3),
            confidence=confidence_score,
            confidence_factors=factors
        )
    }