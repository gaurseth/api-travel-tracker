import re
from models.common import ExtractedValue, ConfidenceFactors
from scoring.confidence import compute_confidence

# Titles that may appear attached to or separated from the name
_TITLES = (
    "MASTER", "MSTR", "MISS", "MRS", "MR", "MS",
    "PROF", "LADY", "LORD", "CAPT", "REV",
    "DR", "SIR", "INF", "CHD",
)
# Longer titles first so "MASTER" matches before "MR", "MISS" before "MS", etc.
_TITLE_PATTERN = "|".join(_TITLES)


def strip_title(name: str):
    """
    Strip a title from a name string. Handles both separated and attached cases:
      "GAURAV MR"  -> ("GAURAV", "MR")
      "GAURAVMR"   -> ("GAURAV", "MR")
      "GAURAV"     -> ("GAURAV", None)
    """
    # Case 1: title separated by space (e.g. "GAURAV MR")
    m = re.match(rf"^(.+?)\s+({_TITLE_PATTERN})$", name)
    if m:
        return m.group(1).strip(), m.group(2)

    # Case 2: title attached at the end (e.g. "GAURAVMR")
    m = re.match(rf"^(.+?)({_TITLE_PATTERN})$", name)
    if m and len(m.group(1)) >= 2:  # name part must be at least 2 chars
        return m.group(1), m.group(2)

    return name, None


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
    # Match LAST/FIRST with optional title (attached or separated)
    name_match = re.search(
        r"\b([A-Z]{2,})\/([A-Z]{2,}(?:\s*(?:" + _TITLE_PATTERN + r"))?)\b",
        text
    )

    if not name_match:
        return {
            "lastName": ExtractedValue(value=None, confidence=0.0, confidence_factors=None),
            "firstName": ExtractedValue(value=None, confidence=0.0, confidence_factors=None),
            "title": ExtractedValue(value=None, confidence=0.0, confidence_factors=None),
        }

    raw_last = name_match.group(1)
    raw_first = name_match.group(2)

    # Strip title from both parts (title usually on first name side but clean both)
    last_name, title_from_last = strip_title(raw_last)
    first_name, title_from_first = strip_title(raw_first)

    title = title_from_first or title_from_last

    factors = ConfidenceFactors(
        ocr=ocr_conf,
        pattern=1.0,
        context=0.9,   # slightly higher context since format is usually standardized
        airline=0.0    # airline factor not relevant here
    )

    confidence_score = compute_confidence(factors)

    return {
        "lastName": ExtractedValue(
            value=last_name,
            confidence=confidence_score,
            confidence_factors=factors
        ),
        "firstName": ExtractedValue(
            value=first_name,
            confidence=confidence_score,
            confidence_factors=factors
        ),
        "title": ExtractedValue(
            value=title,
            confidence=confidence_score,
            confidence_factors=factors
        )
    }
