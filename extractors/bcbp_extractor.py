"""
IATA Bar Coded Boarding Pass (BCBP) Parser

Parses BCBP format strings according to IATA Resolution 792.
Barcode scanning is handled by the frontend; this module only
converts the raw BCBP string into structured data.
"""
from typing import Optional, Dict
from datetime import datetime, timedelta


class BCBPParser:
    """
    Parse IATA Bar Coded Boarding Pass (BCBP) format strings.

    Reference: IATA Resolution 792
    Format: M<num_legs><passenger_name><e_ticket><pnr><segment_data>...

    Example:
    M1SMITH/JOHN          EABC123 DXBJFKEK 0202 123Y012A0001 100
    """

    @staticmethod
    def parse(bcbp_string: str) -> Optional[Dict]:
        """
        Parse BCBP format string.

        Args:
            bcbp_string: Raw BCBP data from barcode

        Returns:
            Parsed data dict with passenger info and segments, or None if invalid
        """
        if not bcbp_string or not bcbp_string.startswith('M'):
            return None

        try:
            parsed = {
                "format_code": bcbp_string[0],  # Always 'M'
                "num_segments": int(bcbp_string[1]),
                "raw_bcbp": bcbp_string,
                "extraction_method": "barcode_pdf417",
                "segments": []
            }

            # Parse mandatory section (positions 2-60)
            if len(bcbp_string) < 60:
                return None

            # Passenger name (positions 2-22, 20 characters)
            passenger_name = bcbp_string[2:22].strip()
            parsed["passenger_name"] = passenger_name

            # Parse passenger name (Last/First format)
            if '/' in passenger_name:
                parts = passenger_name.split('/', 1)
                parsed["passenger_last_name"] = parts[0].strip()
                parsed["passenger_first_name"] = parts[1].strip()

            # Electronic ticket indicator (position 22)
            parsed["electronic_ticket"] = bcbp_string[22] if len(bcbp_string) > 22 else None

            # PNR/Booking reference (positions 23-29, 7 characters)
            parsed["pnr"] = bcbp_string[23:30].strip()

            # Parse each flight segment
            num_segments = parsed["num_segments"]
            pos = 30  # Start position of first segment

            for segment_num in range(1, num_segments + 1):
                # Each segment requires minimum 36 characters
                if len(bcbp_string) < pos + 36:
                    break

                segment = BCBPParser._parse_segment(bcbp_string, pos, segment_num)
                if segment:
                    parsed["segments"].append(segment)

                # Advance by 36 chars (mandatory section per segment)
                pos += 36

            return parsed if parsed["segments"] else None

        except Exception as e:
            print(f"⚠️  Error parsing BCBP string: {e}")
            return None

    @staticmethod
    def _parse_segment(bcbp_string: str, pos: int, segment_number: int) -> Optional[Dict]:
        """
        Parse a single flight segment from BCBP data.

        Segment structure (36 characters minimum):
        - Origin (3): Airport code
        - Destination (3): Airport code
        - Airline (3): Carrier code
        - Flight number (5): Flight number
        - Julian date (3): Day of year (001-366)
        - Cabin class (1): Y/J/F/etc.
        - Seat (4): Seat number
        - Sequence (5): Check-in sequence number
        - Passenger status (1): Status code
        - Variable size field length (2): Conditional section size
        """
        try:
            segment = {"segment_number": segment_number}

            segment["origin"]        = bcbp_string[pos:pos+3].strip()
            segment["destination"]   = bcbp_string[pos+3:pos+6].strip()
            segment["airline_code"]  = bcbp_string[pos+6:pos+9].strip()
            segment["flight_number"] = bcbp_string[pos+9:pos+14].strip()

            julian_date_str = bcbp_string[pos+14:pos+17]
            if julian_date_str.isdigit():
                segment["julian_date"]    = julian_date_str
                segment["departure_date"] = BCBPParser._julian_to_date(julian_date_str)

            segment["cabin_class"]        = bcbp_string[pos+17] if len(bcbp_string) > pos+17 else None
            seat                          = bcbp_string[pos+18:pos+22].strip()
            segment["seat"]               = seat if seat else None
            segment["checkin_sequence"]   = bcbp_string[pos+22:pos+27].strip()
            segment["passenger_status"]   = bcbp_string[pos+27] if len(bcbp_string) > pos+27 else None

            return segment

        except Exception as e:
            print(f"⚠️  Error parsing segment {segment_number}: {e}")
            return None

    @staticmethod
    def _julian_to_date(julian_str: str) -> Optional[str]:
        """
        Convert Julian date (day of year) to ISO-8601 date.

        Assumes current year; shifts to next year if the date is
        more than 6 months in the past.
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
