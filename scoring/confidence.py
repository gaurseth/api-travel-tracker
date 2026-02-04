from models.common import ConfidenceFactors

def compute_confidence(factors: ConfidenceFactors) -> float:
    """
    Computes a weighted confidence score (0.0 - 1.0) for a field.
    """
    return round(
        0.35 * factors.ocr +
        0.35 * factors.pattern +
        0.15 * factors.context +
        0.15 * factors.airline,
        2
    )
