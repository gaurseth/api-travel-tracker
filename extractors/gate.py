import re
from models.common import ExtractedValue, ConfidenceFactors
from scoring.confidence import compute_confidence

def extract_gate(text: str, ocr_conf: float = 1.0):
    """
    Extracts gate number (e.g., C14, A5, 23).
    Returns ExtractedValue object.
    """
    # Look for gate with context keyword
    gate_with_context = re.search(r"(?:GATE|GTI)[:\s]+([A-Z]?\d{1,3}[A-Z]?)\b", text, re.IGNORECASE)

    if gate_with_context:
        gate_value = gate_with_context.group(1).upper()

        factors = ConfidenceFactors(
            ocr=ocr_conf,
            pattern=0.95,
            context=0.95,  # Has "GATE" keyword
            airline=0.85
        )

        confidence_score = compute_confidence(factors)

        return ExtractedValue(
            value=gate_value,
            confidence=confidence_score,
            confidence_factors=factors
        )

    # Fallback: just a terminal + number pattern
    gate_pattern = re.search(r"\b([A-Z]\d{1,2})\b", text)
    if gate_pattern:
        gate_value = gate_pattern.group(1)

        factors = ConfidenceFactors(
            ocr=ocr_conf,
            pattern=0.7,   # Weaker without keyword
            context=0.5,   # No "GATE" keyword
            airline=0.75
        )

        confidence_score = compute_confidence(factors)

        return ExtractedValue(
            value=gate_value,
            confidence=confidence_score,
            confidence_factors=factors
        )

    return ExtractedValue(value=None, confidence=0.0, confidence_factors=None)
