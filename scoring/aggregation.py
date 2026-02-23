"""
Confidence aggregation for overall boarding pass extraction quality.
"""
from typing import List, Tuple
from models.boarding_pass import BoardingPass
from models.common import Warning


# Field importance weights (must sum to 1.0)
FIELD_WEIGHTS = {
    "passenger_name": 0.20,
    "flight_number": 0.20,
    "date": 0.15,
    "route": 0.15,
    "seat": 0.08,
    "gate": 0.07,
    "boarding_time": 0.05,
    "pnr": 0.10,
}


def compute_overall_confidence(boarding_pass: BoardingPass) -> Tuple[float, List[Warning]]:
    """
    Computes weighted overall confidence score for a boarding pass.

    Returns:
        Tuple of (overall_confidence, warnings)
        - overall_confidence: float between 0.0 and 1.0
        - warnings: list of Warning objects for low-confidence or missing fields
    """
    scores = []
    weights = []
    warnings = []

    # Passenger Name (weight: 0.20)
    if boarding_pass.passenger and boarding_pass.passenger.full_name:
        conf = boarding_pass.passenger.full_name.confidence
        scores.append(conf)
        weights.append(FIELD_WEIGHTS["passenger_name"])

        if conf < 0.75:
            warnings.append(Warning(
                field="passenger_name",
                reason="Low confidence passenger name extraction",
                confidence=conf
            ))
    else:
        warnings.append(Warning(
            field="passenger_name",
            reason="Passenger name not found",
            confidence=0.0
        ))

    # Flight Number (weight: 0.20)
    if boarding_pass.flight and boarding_pass.flight.flight_number:
        conf = boarding_pass.flight.flight_number.confidence
        scores.append(conf)
        weights.append(FIELD_WEIGHTS["flight_number"])

        if conf < 0.75:
            warnings.append(Warning(
                field="flight_number",
                reason="Low confidence flight number extraction",
                confidence=conf
            ))
    else:
        warnings.append(Warning(
            field="flight_number",
            reason="Flight number not found",
            confidence=0.0
        ))

    # Date (weight: 0.15)
    if boarding_pass.flight and boarding_pass.flight.date:
        conf = boarding_pass.flight.date.confidence
        scores.append(conf)
        weights.append(FIELD_WEIGHTS["date"])

        if conf < 0.75:
            warnings.append(Warning(
                field="date",
                reason="Low confidence date extraction",
                confidence=conf
            ))
    else:
        warnings.append(Warning(
            field="date",
            reason="Flight date not found",
            confidence=0.0
        ))

    # Route (weight: 0.15)
    if boarding_pass.route and boarding_pass.route.origin and boarding_pass.route.destination:
        origin_conf = boarding_pass.route.origin.iata.confidence
        dest_conf = boarding_pass.route.destination.iata.confidence
        route_conf = min(origin_conf, dest_conf)
        scores.append(route_conf)
        weights.append(FIELD_WEIGHTS["route"])

        if route_conf < 0.75:
            warnings.append(Warning(
                field="route",
                reason="Low confidence route extraction",
                confidence=route_conf
            ))
    else:
        warnings.append(Warning(
            field="route",
            reason="Route information incomplete or missing",
            confidence=0.0
        ))

    # Seat (weight: 0.08)
    if boarding_pass.boarding and boarding_pass.boarding.seat:
        conf = boarding_pass.boarding.seat.confidence
        scores.append(conf)
        weights.append(FIELD_WEIGHTS["seat"])

        if conf < 0.70:  # Lower threshold for optional field
            warnings.append(Warning(
                field="seat",
                reason="Low confidence seat extraction",
                confidence=conf
            ))
    # Seat is optional, no warning if missing

    # Gate (weight: 0.07)
    if boarding_pass.boarding and boarding_pass.boarding.gate:
        conf = boarding_pass.boarding.gate.confidence
        scores.append(conf)
        weights.append(FIELD_WEIGHTS["gate"])

        if conf < 0.70:
            warnings.append(Warning(
                field="gate",
                reason="Low confidence gate extraction",
                confidence=conf
            ))
    # Gate is optional, no warning if missing

    # Boarding Time (weight: 0.05)
    if boarding_pass.boarding and boarding_pass.boarding.time:
        conf = boarding_pass.boarding.time.confidence
        scores.append(conf)
        weights.append(FIELD_WEIGHTS["boarding_time"])

        if conf < 0.70:
            warnings.append(Warning(
                field="boarding_time",
                reason="Low confidence boarding time extraction",
                confidence=conf
            ))
    # Boarding time is optional, no warning if missing

    # PNR (weight: 0.10)
    if boarding_pass.pnr:
        conf = boarding_pass.pnr.confidence
        scores.append(conf)
        weights.append(FIELD_WEIGHTS["pnr"])

        if conf < 0.70:
            warnings.append(Warning(
                field="pnr",
                reason="Low confidence PNR extraction",
                confidence=conf
            ))
    # PNR is optional but valuable, no warning if missing

    # Calculate weighted average
    if not scores:
        return 0.0, warnings

    # Normalize weights to sum to 1.0 (in case some fields are missing)
    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0, warnings

    normalized_weights = [w / total_weight for w in weights]

    # Weighted sum
    overall_confidence = sum(score * weight for score, weight in zip(scores, normalized_weights))

    return round(overall_confidence, 2), warnings


def get_extraction_quality_label(confidence: float) -> str:
    """
    Returns a human-readable quality label based on confidence score.
    """
    if confidence >= 0.90:
        return "excellent"
    elif confidence >= 0.75:
        return "good"
    elif confidence >= 0.60:
        return "medium"
    else:
        return "low"


def should_trigger_ai_fallback(confidence: float) -> bool:
    """
    Determines if AI fallback should be triggered based on overall confidence.
    """
    return confidence < 0.75
