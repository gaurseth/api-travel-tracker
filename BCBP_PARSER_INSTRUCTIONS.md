# BCBP Multi-Segment Parser — Rewrite Instructions for Claude Code

## Objective

Rewrite the IATA BCBP (Bar Coded Boarding Pass) parser to correctly handle multi-segment boarding passes (1–8 segments). The current parser fails to locate and parse second (and subsequent) segment data. This document explains the exact structure and logic required.

---

## Key Concept: Why Multi-Segment Parsing Breaks

The BCBP format has **variable-length conditional data** after each segment's mandatory fields. The length of this conditional block is encoded as a **2-character hex value**. If you don't read this hex value and use it to calculate offsets, you'll read segment 2+ data from the wrong position.

---

## BCBP String Structure Overview

A BCBP string is composed of these sections in order:

```
[Mandatory Unique - shared]  (22 chars)
[Mandatory Unique - seg 1]  (37 chars)
[Hex size field]             (2 chars)
[Conditional data - seg 1]  (variable length, from hex)
[Mandatory Unique - seg 2]  (37 chars)   ← only if segments >= 2
[Hex size field]             (2 chars)
[Conditional data - seg 2]  (variable length)
... repeat for more segments
```

---

## Section 1: Mandatory Unique Fields (Shared Header)

These appear **once** at the start of the string, shared across all segments.

| Field                    | Length | Offset (0-based) | Notes                              |
|--------------------------|--------|-------------------|------------------------------------|
| Format code              | 1      | 0                 | Always `M`                         |
| Number of legs/segments  | 1      | 1                 | `1`–`8`                            |
| Passenger name           | 20     | 2–21              | `LAST/FIRST TITLE`, space-padded   |

**Total: 22 characters**

---

## Section 2: Mandatory Unique Fields (Per Segment — First Segment)

These follow immediately after the shared header for segment 1.

| Field                              | Length | Offset (0-based) | Notes                                |
|------------------------------------|--------|-------------------|--------------------------------------|
| Electronic ticket indicator        | 1      | 22                | Usually `E`                          |
| Operating carrier PNR code         | 7      | 23–29             | Space-padded                         |
| Origin airport (IATA)              | 3      | 30–32             |                                      |
| Destination airport (IATA)         | 3      | 33–35             |                                      |
| Operating carrier designator       | 3      | 36–38             | Space-padded                         |
| Flight number                      | 5      | 39–43             | Space-padded                         |
| Date of flight (Julian)            | 3      | 44–46             | Day of year, e.g., `023` = Jan 23   |
| Compartment code                   | 1      | 47                | `F`, `J`, `Y`, etc.                 |
| Seat number                        | 4      | 48–51             | e.g., `024C`                         |
| Check-in sequence number           | 5      | 52–56             | Space-padded                         |
| Passenger status                   | 1      | 57                |                                      |
| **Size of variable field (hex)**   | **2**  | **58–59**         | **THIS IS THE CRITICAL FIELD**       |

**Total: 38 characters (offset 22–59)**

---

## Section 3: Conditional/Variable Data (Segment 1)

- Starts at offset **60**
- Length = `parseInt(barcode.substring(58, 60), 16)` — convert the 2-char hex to decimal
- This block contains optional fields like: version number indicator (`>`), version number, field size of structured message (unique), field size of structured message (repeated), airline-specific data, frequent flyer info, ID/AD indicator, free baggage allowance, fast track, ticket number, etc.
- **You do NOT need to parse every field inside this block** to find the next segment. Just skip over it using the calculated length.

### Parsing the Conditional Block (Optional Detail)

If you want to parse conditional fields, the block starts with:

| Field                                         | Length | Notes                                      |
|-----------------------------------------------|--------|--------------------------------------------|
| Beginning of version number (`>`)             | 1      | Always `>`                                 |
| Version number                                | 1      | e.g., `8`                                  |
| Unique conditional field size (hex)           | 2      | Length of unique conditional fields         |
| Passenger description                         | 1      |                                            |
| Source of check-in                            | 1      |                                            |
| Source of boarding pass issuance              | 1      |                                            |
| Date of issue of boarding pass (Julian)       | 4      |                                            |
| Document type                                 | 1      |                                            |
| Airline designator of boarding pass issuer    | 3      |                                            |
| Baggage tag license plate number(s)           | 13     |                                            |
| 1st non-consecutive seat                      | 4      |                                            |
| ...then repeated conditional size (hex)       | 2      | Length of repeated conditional fields       |
| ...then repeated conditional fields           | var    | Airline-specific, frequent flyer, etc.     |

But again — **for locating the next segment, you only need the hex size at offsets 58–59**.

---

## Section 4: Subsequent Segments (Segment 2, 3, etc.)

### How to Find Segment N

```
segment2_start = 60 + parseInt(barcode.substring(58, 60), 16)
```

At `segment2_start`, you'll find **repeated mandatory fields** (note: NO shared header fields, NO electronic ticket indicator):

| Field                              | Length | Relative Offset | Notes                            |
|------------------------------------|--------|------------------|----------------------------------|
| Operating carrier PNR code         | 7      | 0–6              | Space-padded                     |
| Origin airport (IATA)              | 3      | 7–9              |                                  |
| Destination airport (IATA)         | 3      | 10–12            |                                  |
| Operating carrier designator       | 3      | 13–15            | Space-padded                     |
| Flight number                      | 5      | 16–20            | Space-padded                     |
| Date of flight (Julian)            | 3      | 21–23            |                                  |
| Compartment code                   | 1      | 24               |                                  |
| Seat number                        | 4      | 25–28            |                                  |
| Check-in sequence number           | 5      | 29–33            |                                  |
| Passenger status                   | 1      | 34               |                                  |
| **Size of variable field (hex)**   | **2**  | **35–36**        | Hex length of seg 2 conditional  |

**Total: 37 characters per repeated segment**

Then segment 2's conditional data follows for the length specified by its own hex size field.

### For Segment 3 and Beyond

Repeat the same logic:
```
segment3_start = segment2_start + 37 + parseInt(barcode.substring(segment2_start + 35, segment2_start + 37), 16)
```

---

## Implementation Pseudocode

```javascript
function parseBCBP(barcode) {
  const numSegments = parseInt(barcode[1]);
  
  // --- Shared header ---
  const passengerName = barcode.substring(2, 22).trim();
  
  // --- Segment 1 mandatory ---
  const seg1 = parseSegmentMandatory(barcode, 22, true); // true = first segment (has eTicket indicator)
  
  // --- Segment 1 conditional ---
  const seg1VarHex = barcode.substring(58, 60);
  const seg1VarLength = parseInt(seg1VarHex, 16);
  // Optional: parse conditional fields from barcode.substring(60, 60 + seg1VarLength)
  
  // --- Subsequent segments ---
  let cursor = 60 + seg1VarLength;
  const segments = [seg1];
  
  for (let i = 1; i < numSegments; i++) {
    const seg = parseSegmentMandatory(barcode, cursor, false); // false = repeated segment
    
    const varHex = barcode.substring(cursor + 35, cursor + 37);
    const varLength = parseInt(varHex, 16);
    // Optional: parse conditional fields from barcode.substring(cursor + 37, cursor + 37 + varLength)
    
    segments.push(seg);
    cursor = cursor + 37 + varLength;
  }
  
  return { passengerName, segments };
}

function parseSegmentMandatory(barcode, offset, isFirst) {
  let pos = offset;
  
  // First segment has electronic ticket indicator (1 char)
  let eTicket = null;
  if (isFirst) {
    eTicket = barcode[pos];
    pos += 1;
  }
  
  const pnr = barcode.substring(pos, pos + 7).trim();        pos += 7;
  const origin = barcode.substring(pos, pos + 3);              pos += 3;
  const destination = barcode.substring(pos, pos + 3);         pos += 3;
  const carrier = barcode.substring(pos, pos + 3).trim();      pos += 3;
  const flightNumber = barcode.substring(pos, pos + 5).trim(); pos += 5;
  const julianDate = barcode.substring(pos, pos + 3);          pos += 3;
  const compartment = barcode[pos];                             pos += 1;
  const seat = barcode.substring(pos, pos + 4).trim();         pos += 4;
  const checkInSeq = barcode.substring(pos, pos + 5).trim();   pos += 5;
  const passengerStatus = barcode[pos];                         pos += 1;
  // Next 2 chars are the hex size of variable field (parsed by caller)
  
  return {
    eTicket,
    pnr,
    origin,
    destination,
    carrier,
    flightNumber,
    julianDate,
    compartment,
    seat,
    checkInSeq,
    passengerStatus,
  };
}
```

---

## Test Case

Use this known-good string to validate your parser:

```
M2SETH/MYRA MISS      ECRYFTC NBJADDET 0850 023Y024C0127 177>8322MO6023BET                                        2A0712157854092 1ET                        N*306      0900       CRYFTC ADDDELET 0686 023Y025J0094 12C290712157854092 1ET                        N
```

### Expected Output

```
Passenger: SETH/MYRA MISS
Number of segments: 2

Segment 1:
  PNR:         CRYFTC
  Origin:      NBJ
  Destination: ADD
  Carrier:     ET
  Flight:      0850
  Julian Date: 023
  Compartment: Y
  Seat:        024C
  Sequence:    0127
  Status:      1
  Var size:    0x77 = 119

Segment 2 (starts at offset 60 + 119 = 179):
  PNR:         CRYFTC
  Origin:      ADD
  Destination: DEL
  Carrier:     ET
  Flight:      0686
  Julian Date: 023
  Compartment: Y
  Seat:        025J
  Sequence:    0094
  Status:      1
```

---

## Common Pitfalls to Avoid

1. **Hardcoding segment 2 offset** — The offset is ALWAYS dynamic based on the hex size field. Never assume a fixed position.
2. **Forgetting that segment 1 has an extra field** — The electronic ticket indicator (1 char) is only present in segment 1's mandatory block. Repeated segments do NOT have it. This means segment 1 mandatory is 38 chars (including hex size) but repeated segments are 37 chars.
3. **Treating hex size as decimal** — `77` means 119, not 77. Always use `parseInt(value, 16)`.
4. **Not trimming fields** — PNR, carrier, flight number, and seat are space-padded. Always `.trim()`.
5. **Off-by-one errors** — Use 0-based indexing consistently with `substring(start, end)` where `end` is exclusive.
6. **Julian date interpretation** — The 3-digit Julian date is the day of the year (001–366). The year is NOT encoded in the mandatory fields; it may appear in the conditional data or must be inferred.

---

## Summary

The single most important thing: **read the 2-character hex field at the end of each segment's mandatory block to calculate where the next segment begins.** Everything else follows from getting this offset calculation right.
