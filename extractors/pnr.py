import re
from models.common import ExtractedValue, ConfidenceFactors
from scoring.confidence import compute_confidence

def extract_pnr(text: str, ocr_conf: float = 1.0):
    """
    Extracts PNR/Booking Reference (typically 5-6 alphanumeric characters).
    Returns ExtractedValue object.
    """
    # Look for PNR with context keywords
    pnr_patterns = [
        (r"(?:PNR|BOOKING\s+REF|REFERENCE|REC\s+LOC)[:\s]+([A-Z0-9]{5,6})\b", 0.95),  # With keyword
        (r"\b([A-Z0-9]{6})\b", 0.7),  # 6-char alphanumeric (lower confidence, could be anything)
    ]

    for pattern, context_score in pnr_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            pnr_value = match.group(1).upper()

            factors = ConfidenceFactors(
                ocr=ocr_conf,
                pattern=0.85,
                context=context_score,
                airline=0.8
            )

            confidence_score = compute_confidence(factors)

            return ExtractedValue(
                value=pnr_value,
                confidence=confidence_score,
                confidence_factors=factors
            )

    return ExtractedValue(value=None, confidence=0.0, confidence_factors=None)


def extract_ticket_number(text: str, ocr_conf: float = 1.0):
    """
    Extracts ticket number (typically 13 digits: 3-digit airline code + 10 digits).
    Returns ExtractedValue object.
    """
    ticket_match = re.search(r"\b(\d{3})\s?(\d{10})\b", text)

    if not ticket_match:
        return ExtractedValue(value=None, confidence=0.0, confidence_factors=None)

    ticket_value = f"{ticket_match.group(1)}{ticket_match.group(2)}"

    factors = ConfidenceFactors(
        ocr=ocr_conf,
        pattern=1.0,   # Very specific pattern
        context=0.8,
        airline=0.9    # Ticket format is standardized
    )

    confidence_score = compute_confidence(factors)

    return ExtractedValue(
        value=ticket_value,
        confidence=confidence_score,
        confidence_factors=factors
    )
