"""
IATA Bar Coded Boarding Pass (BCBP) Parser

Parses BCBP format strings according to IATA Resolution 792.
Correctly handles multi-segment boarding passes (1–8 segments)
by reading the variable-length conditional data hex size at the
end of each segment's mandatory block to locate the next segment.

String layout:
    [Shared header]           22 chars  (offsets 0–21)
    [Segment 1 mandatory]     38 chars  (offsets 22–59, includes 2-char hex size at 58–59)
    [Segment 1 conditional]   variable  (length = int("77", 16) etc.)
    [Segment 2 mandatory]     37 chars  (no e-ticket indicator; hex size at relative offset 35–36)
    [Segment 2 conditional]   variable
    ... repeat for segments 3–8
"""
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
from extractors.passenger_name import strip_title


class BCBPParser:
    """Parse IATA BCBP format strings (IATA Resolution 792)."""

    @staticmethod
    def parse(bcbp_string: str) -> Optional[Dict]:
        """
        Parse a full BCBP string into structured data.

        Args:
            bcbp_string: Raw BCBP string from a PDF417 barcode scan. Must start with 'M'.

        Returns:
            Dict with passenger info and a list of segment dicts, or None if invalid.
        """
        if not bcbp_string or not bcbp_string.startswith('M'):
            return None

        try:
            num_segments = int(bcbp_string[1])
        except (ValueError, IndexError):
            return None

        # Minimum viable length: shared header (22) + seg 1 mandatory (38) = 60
        if len(bcbp_string) < 60:
            return None

        try:
            # ------------------------------------------------------------------
            # Shared header  (offsets 0–21)
            # ------------------------------------------------------------------
            passenger_name_raw = bcbp_string[2:22].strip()
            passenger_last = passenger_first = None
            if '/' in passenger_name_raw:
                parts = passenger_name_raw.split('/', 1)
                passenger_last, _  = strip_title(parts[0].strip())
                passenger_first, _ = strip_title(parts[1].strip())
            passenger_name = f"{passenger_last}/{passenger_first}" if passenger_last else passenger_name_raw

            # ------------------------------------------------------------------
            # Segment 1 mandatory  (offsets 22–59)
            # e-ticket indicator at offset 22 is only present in segment 1.
            # ------------------------------------------------------------------
            seg1, seg1_var_hex = BCBPParser._parse_segment_mandatory(
                bcbp_string, offset=22, is_first=True, segment_number=1
            )

            # 2-char hex at offsets 58–59 → decimal length of seg 1 conditional block
            seg1_var_length = int(seg1_var_hex, 16)

            segments = [seg1]

            # ------------------------------------------------------------------
            # Subsequent segments  (segment 2, 3, …)
            # Each starts immediately after the previous segment's conditional block.
            # ------------------------------------------------------------------
            cursor = 60 + seg1_var_length  # start of segment 2 mandatory block

            for seg_num in range(2, num_segments + 1):
                # Repeated segment mandatory block is 37 chars
                if cursor + 37 > len(bcbp_string):
                    print(f"⚠️  BCBP string too short for segment {seg_num} (cursor={cursor}, len={len(bcbp_string)})")
                    break

                seg, var_hex = BCBPParser._parse_segment_mandatory(
                    bcbp_string, offset=cursor, is_first=False, segment_number=seg_num
                )
                segments.append(seg)

                var_length = int(var_hex, 16)
                cursor = cursor + 37 + var_length  # advance past mandatory + conditional

            return {
                "format_code":          "M",
                "num_segments":         num_segments,
                "raw_bcbp":             bcbp_string,
                "extraction_method":    "barcode_pdf417",
                "passenger_name":       passenger_name,
                "passenger_last_name":  passenger_last,
                "passenger_first_name": passenger_first,
                "electronic_ticket":    seg1.get("electronic_ticket"),
                # Top-level PNR = segment 1's PNR (most common use-case)
                "pnr":                  seg1.get("pnr"),
                "segments":             segments,
            }

        except Exception as e:
            print(f"⚠️  Error parsing BCBP string: {e}")
            return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_segment_mandatory(
        bcbp_string: str,
        offset: int,
        is_first: bool,
        segment_number: int,
    ) -> Tuple[Dict, str]:
        """
        Parse the mandatory fields of one segment and return the hex size of its
        conditional block so the caller can skip past it.

        Segment 1 layout (is_first=True, offset=22):
            offset+0:  e-ticket indicator  (1)
            offset+1:  PNR                 (7)
            offset+8:  origin              (3)
            offset+11: destination         (3)
            offset+14: carrier             (3)
            offset+17: flight number       (5)
            offset+22: Julian date         (3)
            offset+25: compartment code    (1)
            offset+26: seat number         (4)
            offset+30: check-in sequence   (5)
            offset+35: passenger status    (1)
            offset+36: hex size            (2)  ← at absolute offsets 58–59
            Total: 38 chars

        Segment 2+ layout (is_first=False):
            offset+0:  PNR                 (7)
            offset+7:  origin              (3)
            offset+10: destination         (3)
            offset+13: carrier             (3)
            offset+18: flight number       (5)  — note: 13+3=16, not 18
            ... (see below)
            Total: 37 chars

        Returns:
            (segment_dict, var_hex)  where var_hex is the 2-char hex string.
        """
        pos = offset

        # Electronic ticket indicator — only in segment 1
        e_ticket = None
        if is_first:
            e_ticket = bcbp_string[pos]
            pos += 1

        # Fields common to all segments
        pnr             = bcbp_string[pos:pos+7].strip();  pos += 7
        origin          = bcbp_string[pos:pos+3].strip();  pos += 3
        destination     = bcbp_string[pos:pos+3].strip();  pos += 3
        airline_code    = bcbp_string[pos:pos+3].strip();  pos += 3
        flight_number   = bcbp_string[pos:pos+5].strip();  pos += 5
        julian_str      = bcbp_string[pos:pos+3];          pos += 3
        compartment     = bcbp_string[pos];                 pos += 1
        seat            = bcbp_string[pos:pos+4].strip();  pos += 4
        checkin_seq     = bcbp_string[pos:pos+5].strip();  pos += 5
        passenger_status= bcbp_string[pos];                 pos += 1
        var_hex         = bcbp_string[pos:pos+2]           # do NOT advance pos — caller uses this

        departure_date = BCBPParser._julian_to_date(julian_str) if julian_str.isdigit() else None

        segment = {
            "segment_number":   segment_number,
            "electronic_ticket": e_ticket,
            "pnr":               pnr,
            "origin":            origin,
            "destination":       destination,
            "airline_code":      airline_code,
            "flight_number":     flight_number,
            "julian_date":       julian_str,
            "departure_date":    departure_date,
            "cabin_class":       compartment,
            "seat":              seat if seat else None,
            "checkin_sequence":  checkin_seq,
            "passenger_status":  passenger_status,
        }

        return segment, var_hex

    @staticmethod
    def _julian_to_date(julian_str: str) -> Optional[str]:
        """
        Convert a 3-digit Julian day-of-year to an ISO-8601 date string.

        The year is not encoded in the mandatory block; we assume the current
        year and shift to next year if the resulting date is more than 6 months
        in the past (handles year-boundary bookings).
        """
        try:
            julian_day = int(julian_str)
            if not (1 <= julian_day <= 366):
                return None

            current_date = datetime.now()
            year = current_date.year
            date = datetime(year, 1, 1) + timedelta(days=julian_day - 1)

            if date < current_date - timedelta(days=180):
                date = datetime(year + 1, 1, 1) + timedelta(days=julian_day - 1)

            return date.strftime("%Y-%m-%d")

        except Exception:
            return None
