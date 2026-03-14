"""
LLM-based boarding pass extractor using Claude vision.

Fallback for when OCR confidence is low. Sends the boarding pass image
(+ optional barcode context) to Claude and asks for structured JSON.
"""
import os
import json
import base64
from typing import List, Dict, Any, Optional, Tuple

import anthropic


# The exact JSON schema the LLM must return — matches _SEGMENT_KEYS in trip_service.py
_SEGMENT_SCHEMA = {
    "origin": "3-letter IATA airport code for departure airport (e.g. 'FRA', 'JFK')",
    "destination": "3-letter IATA airport code for arrival airport (e.g. 'IAH', 'LHR')",
    "airline_code": "2-3 character airline code (e.g. 'LH', 'UA', '6E')",
    "flight_number": "Flight number digits only, no airline prefix (e.g. '0047', '2590')",
    "departure_date": "Departure date in ISO format YYYY-MM-DD (e.g. '2026-05-03')",
    "departure_time": "Departure time in HH:MM 24h format (e.g. '14:30') or null if not visible",
    "arrival_date": "Arrival date in ISO format YYYY-MM-DD or null if not visible",
    "arrival_time": "Arrival time in HH:MM 24h format or null if not visible",
    "seat": "Seat number (e.g. '24C', '1A') or null if not visible",
    "gate": "Gate number/letter (e.g. 'B12', 'A3') or null if not visible",
    "boarding_time": "Boarding time in HH:MM 24h format or null if not visible",
    "pnr": "PNR / booking reference code (e.g. 'CRYFTC', 'ABC123') or null if not visible",
    "cabin_class": "Cabin class single letter code (Y=economy, J=business, F=first) or null",
    "passenger_name": "Passenger name as shown on boarding pass (e.g. 'SETH/GAURAV') or null",
}

_SCHEMA_JSON = json.dumps(_SEGMENT_SCHEMA, indent=2)

# Lazy-initialised client
_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Add it to .env to enable LLM fallback."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _build_system_prompt() -> str:
    return (
        "You are a boarding pass data extractor. You will be given an image of "
        "a boarding pass (and optionally some context from a barcode scan). "
        "Extract all flight segment information visible on the boarding pass.\n\n"
        "Return ONLY a valid JSON object with no explanation, no markdown fences, "
        "no extra text. The JSON must have this exact structure:\n\n"
        "{\n"
        '  "segments": [ ... array of segment objects ... ]\n'
        "}\n\n"
        "Each segment object must have exactly these keys (use null for any field "
        "you cannot determine):\n\n"
        f"{_SCHEMA_JSON}\n\n"
        "Rules:\n"
        "- IATA codes must be exactly 3 uppercase letters\n"
        "- Dates must be ISO format: YYYY-MM-DD\n"
        "- Times must be 24h format: HH:MM\n"
        "- Flight number should be digits only (no airline prefix)\n"
        "- If the year is not visible, infer it from context (current year or next)\n"
        "- Return one object per flight segment on the boarding pass\n"
        "- Do NOT invent data. If a field is not visible, use null\n"
    )


def _build_user_content(
    image_bytes: bytes,
    raw_ocr_text: str = "",
    barcode_context: Optional[Dict[str, Any]] = None,
) -> list:
    """Build the multimodal user message content blocks."""
    # Detect image type from magic bytes
    if image_bytes[:4] == b'\x89PNG':
        media_type = "image/png"
    elif image_bytes[:2] == b'\xff\xd8':
        media_type = "image/jpeg"
    else:
        media_type = "image/jpeg"  # default fallback

    content = []

    # Image block
    content.append({
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.b64encode(image_bytes).decode("utf-8"),
        },
    })

    # Text instructions + context
    text_parts = ["Extract all flight segment data from this boarding pass image."]

    if barcode_context:
        text_parts.append(
            "\n--- BARCODE CONTEXT (from PDF417 scan of the same boarding pass) ---\n"
            f"Number of segments identified: {barcode_context.get('num_segments', 'unknown')}\n"
            f"Passenger name: {barcode_context.get('passenger_name', 'unknown')}\n"
            f"PNR: {barcode_context.get('pnr', 'unknown')}\n"
        )
        bc_segments = barcode_context.get("segments", [])
        if bc_segments:
            text_parts.append("Segments from barcode:")
            for i, seg in enumerate(bc_segments, 1):
                text_parts.append(
                    f"  Segment {i}: {seg.get('origin', '?')} -> {seg.get('destination', '?')}, "
                    f"flight {seg.get('airline_code', '??')}{seg.get('flight_number', '???')}, "
                    f"date {seg.get('departure_date', '?')}, seat {seg.get('seat', '?')}"
                )
        text_parts.append(
            "\nUse this barcode data as ground truth for routes, flights, and PNR. "
            "Focus on extracting the fields the barcode does NOT provide: "
            "departure_time, arrival_time, arrival_date, gate, boarding_time."
        )

    if raw_ocr_text:
        text_parts.append(
            "\n--- RAW OCR TEXT (may contain errors) ---\n"
            f"{raw_ocr_text[:2000]}"
        )

    text_parts.append(
        "\n\nReturn the JSON object now. Remember: no markdown, no explanation, "
        "just the raw JSON with a \"segments\" array."
    )

    content.append({"type": "text", "text": "\n".join(text_parts)})

    return content


def extract_segments_from_image(
    image_bytes: bytes,
    raw_ocr_text: str = "",
    barcode_context: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], float]:
    """
    Extract boarding pass segments using Claude vision.

    Args:
        image_bytes: Raw image bytes (JPEG or PNG)
        raw_ocr_text: Raw OCR text to help the LLM cross-reference
        barcode_context: Optional dict with barcode data to guide extraction:
            {
                "num_segments": int,
                "passenger_name": str,
                "pnr": str,
                "segments": [{"origin", "destination", "airline_code",
                              "flight_number", "departure_date", "seat"}, ...]
            }

    Returns:
        (segments, confidence) — segments is a list of flat dicts matching
        _SEGMENT_KEYS, confidence is 0.0-1.0 based on parse success.
    """
    client = _get_client()

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_build_system_prompt(),
        messages=[{
            "role": "user",
            "content": _build_user_content(image_bytes, raw_ocr_text, barcode_context),
        }],
    )

    # Extract text from response
    raw_response = ""
    for block in message.content:
        if block.type == "text":
            raw_response += block.text

    # Parse JSON — strip any markdown fences the LLM may have added
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        # Remove ```json ... ``` wrapper
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"LLM extractor: failed to parse JSON response: {raw_response[:500]}")
        return [], 0.0

    raw_segments = data.get("segments", [])
    if not isinstance(raw_segments, list) or not raw_segments:
        print(f"LLM extractor: no segments in response")
        return [], 0.0

    # Normalise into the standard flat dict shape
    _KEYS = (
        "origin", "destination", "airline_code", "flight_number",
        "departure_date", "departure_time", "arrival_date", "arrival_time",
        "seat", "gate", "boarding_time", "pnr", "cabin_class", "passenger_name",
    )

    segments = []
    for raw_seg in raw_segments:
        seg = {}
        for key in _KEYS:
            val = raw_seg.get(key)
            # Normalise "null" string to None
            if val is None or (isinstance(val, str) and val.strip().lower() in ("null", "")):
                seg[key] = None
            else:
                seg[key] = str(val).strip() if isinstance(val, str) else val
        segments.append(seg)

    # Confidence: if we got valid segments, assign 0.85
    # (lower than barcode 0.98 but higher than low OCR)
    confidence = 0.85 if segments else 0.0

    return segments, confidence
