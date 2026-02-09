import re
from models.common import ExtractedValue, ConfidenceFactors
from scoring.confidence import compute_confidence

MONTHS = (
    "JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|"
    "JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER|"
    "JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC"
)

def extract_date(text: str, ocr_conf: float = 1.0):
    """
    Extracts flight date (day and month).
    Returns a dict with:
    {
        "day": ExtractedValue(...),
        "month": ExtractedValue(...),
        "date_string": ExtractedValue(...)  # Combined format
    }
    """
    date_match = re.search(
        rf"\b(\d{{1,2}})\s+({MONTHS})\b",
        text,
        re.IGNORECASE
    )

    if not date_match:
        return {
            "day": ExtractedValue(value=None, confidence=0.0, confidence_factors=None),
            "month": ExtractedValue(value=None, confidence=0.0, confidence_factors=None),
            "date_string": ExtractedValue(value=None, confidence=0.0, confidence_factors=None)
        }

    day = date_match.group(1)
    month = date_match.group(2).title()

    factors = ConfidenceFactors(
        ocr=ocr_conf,
        pattern=0.9,   # Date format can vary
        context=0.85,  # Dates usually near flight info
        airline=0.8    # Standard across airlines
    )

    confidence_score = compute_confidence(factors)

    return {
        "day": ExtractedValue(
            value=day,
            confidence=confidence_score,
            confidence_factors=factors
        ),
        "month": ExtractedValue(
            value=month,
            confidence=confidence_score,
            confidence_factors=factors
        ),
        "date_string": ExtractedValue(
            value=f"{day} {month}",
            confidence=confidence_score,
            confidence_factors=factors
        )
    }
