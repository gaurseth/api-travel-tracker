# Dedup & Multi-Source Merge Specification

## Overview

Trip data can arrive from three sources. The system must deduplicate segments
(reject true duplicates) and merge enrichment data from different sources into
a single authoritative segment, logging any conflicts.

---

## Data Sources and Priority (lowest to highest)

| Priority | Source tag        | Characteristics |
|----------|------------------|-----------------|
| 1 (low)  | `boarding_pass`  | No year in date, has seat/gate/boarding_time, barcode is authoritative for its fields |
| 2        | `manual`         | User-typed, may be sparse |
| 3 (high) | `email`          | Full dates with year, PNR, ticket number, cabin, times, terminals, aircraft |

---

## Segment Fingerprint — Identity Rule

Two segments are considered the **same flight** when ALL of the following match:

| Field            | Match Rule |
|------------------|------------|
| `origin`         | Exact IATA 3-letter, case-insensitive |
| `destination`    | Exact IATA 3-letter, case-insensitive |
| `flight_number`  | Normalized: strip airline prefix, strip leading zeros, compare digits (e.g. `EK0202` and `0202` and `202` all match) |
| `departure_date` | **Fuzzy month+day**: if either side is missing a year, compare month+day only. If both have a year, years must also match. |

`passenger_name` (normalized) is used as a **tiebreaker only** when a trip has
multiple passengers and a fingerprint matches more than one segment.

---

## Trip-Level Matching — Three-Step Flow

```
1. Compute segment fingerprints for all incoming segments.
2. Search ALL of the user's trips for any segment fingerprint match.
   -> Found? Merge into that trip. Done.
3. No fingerprint match? Call find_matching_trip() (existing logic).
   -> PNR overlap (+50), route continuity (+30), time proximity (+20).
   -> Score >= 40? Attach new segments to that trip.
4. No match at all? Create a new trip.
```

`find_matching_trip()` is kept as a fallback for **route chaining** — e.g.
DXB->LHR scanned first, then LHR->JFK scanned later. Different flights but
same trip. Fingerprint won't match, but route continuity will.

---

## Exact Duplicate Rejection

A submission is **rejected** (not merged) if:

- Same `boarding_pass_id` already attached to any trip (physical re-scan).
- Same segment fingerprint from the **same source type** (e.g. two boarding
  pass scans of the same DXB->LHR EK202 on 14-Feb). Second one is rejected.

A submission is **merged** (not rejected) if:

- Same segment fingerprint from a **different source type** (e.g. boarding
  pass scan + email confirmation for the same flight). Fields are merged
  per the priority rules below.

---

## Field-Level Merge Rules

When two segments match (same fingerprint, different sources):

```
for each field:
    if both have a value and they conflict:
        -> keep the higher-priority source's value
        -> log to conflict_log: {field, kept, discarded, kept_source, discarded_source, timestamp}
    if only one has a value:
        -> take it (enrichment, no conflict)
    if neither has a value:
        -> stays null
```

### Special Field Overrides

| Field                       | Rule |
|-----------------------------|------|
| `departure_date`            | If boarding pass has no year (month+day only), adopt the email/manual year. Email wins on full date conflicts. |
| `seat`, `gate`, `boarding_time` | **Boarding pass wins** regardless of overall priority — these are day-of-travel fields that email doesn't have. |
| `cabin_class`               | Email's `cabin` ("Economy") mapped to code. Boarding pass single-letter RBD wins if present (more specific). |
| `pnr`                       | First non-null wins. On conflict, email wins. |
| `departure_time`, `arrival_time` | Email wins (has both consistently). |
| `aircraft`, `departure_terminal`, `arrival_terminal`, `ticket_number` | Email-only fields — always enrichment, never conflict. |

---

## New Segment Fields

Added to `TripSegment` model and `_SEGMENT_KEYS`:

| Field                | Type              | Purpose |
|----------------------|-------------------|---------|
| `source`             | `Optional[str]`   | `"boarding_pass"`, `"manual"`, `"email"` |
| `ticket_number`      | `Optional[str]`   | From email parser `passengers[].ticketNumber` |
| `aircraft`           | `Optional[str]`   | From email parser |
| `departure_terminal` | `Optional[str]`   | From email parser |
| `arrival_terminal`   | `Optional[str]`   | From email parser |
| `conflict_log`       | `List[dict]`      | Array of conflict records |

### conflict_log entry format

```json
{
  "field": "departure_time",
  "kept": "14:05",
  "discarded": "14:00",
  "kept_source": "email",
  "discarded_source": "boarding_pass",
  "timestamp": "2026-04-17T12:00:00"
}
```

---

## New Endpoint

`POST /ingest/email-booking` — receives email parser `Booking` payload,
normalizes to internal segment format, runs through dedup pipeline.

---

## Implementation Files

| File | Purpose |
|------|---------|
| `services/dedup_service.py`       | Fingerprint computation, duplicate search, field merge, ingest orchestrator |
| `services/email_normalizer.py`    | Converts email parser `Booking` JSON to list of internal segment dicts |
| `models/trip_segment.py`          | New fields added to TripSegment model |
| `services/trip_service.py`        | `_SEGMENT_KEYS` updated, `find_matching_trip()` kept as fallback |
| `main.py`                         | New `/ingest/email-booking` endpoint; `/process-boarding-pass` wired to dedup |

---

## Source Priority Constant

```python
SOURCE_PRIORITY = {
    "boarding_pass": 1,
    "manual": 2,
    "email": 3,
}
```

## Boarding-Pass-Wins Fields (override priority for day-of-travel data)

```python
BOARDING_PASS_WINS_FIELDS = {"seat", "gate", "boarding_time"}
```
