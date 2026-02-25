#!/usr/bin/env python3
"""
Test script for barcode extraction from boarding pass images.
Tests both barcode detection and OCR fallback.
"""
import sys
from pathlib import Path

def test_barcode_extraction(image_path: str):
    """Test barcode extraction with detailed output."""
    print("=" * 60)
    print("BARCODE EXTRACTION TEST")
    print("=" * 60)
    print(f"Image: {image_path}\n")

    # Check if file exists
    if not Path(image_path).exists():
        print(f"❌ Error: File not found: {image_path}")
        return

    # Read image
    print("📖 Reading image file...")
    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    print(f"✅ Image loaded ({len(image_bytes)} bytes)\n")

    # Test 1: Direct barcode detection
    print("-" * 60)
    print("TEST 1: Direct Barcode Detection")
    print("-" * 60)

    try:
        from extractors.bcbp_extractor import extract_bcbp_data

        print("🔍 Attempting barcode detection...")
        bcbp_data = extract_bcbp_data(image_bytes)

        if bcbp_data:
            print("✅ BARCODE DETECTED!\n")
            print("Extracted Data:")
            print("-" * 40)
            print(f"Passenger: {bcbp_data.get('passenger_name', 'N/A')}")
            print(f"PNR: {bcbp_data.get('pnr', 'N/A')}")
            print(f"Segments: {bcbp_data.get('num_segments', 0)}")

            for segment in bcbp_data.get('segments', []):
                print(f"\nSegment {segment.get('segment_number')}:")
                print(f"  Route: {segment.get('origin')} → {segment.get('destination')}")
                print(f"  Flight: {segment.get('airline_code')}{segment.get('flight_number')}")
                print(f"  Date: {segment.get('departure_date')}")
                print(f"  Seat: {segment.get('seat')}")

            print("\nRaw BCBP String:")
            print(bcbp_data.get('raw_bcbp', 'N/A'))
        else:
            print("❌ No barcode detected")

    except ImportError as e:
        print(f"⚠️  Import Error: {e}")
        print("   Make sure pyzbar and zbar are installed")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: OCR extraction
    print("\n" + "-" * 60)
    print("TEST 2: OCR Text Extraction")
    print("-" * 60)

    try:
        from ocr import extract_text

        print("🔍 Extracting text via OCR...")
        ocr_text = extract_text(image_bytes)

        print(f"✅ OCR completed ({len(ocr_text)} characters)\n")
        print("OCR Text Preview (first 500 chars):")
        print("-" * 40)
        print(ocr_text[:500])
        if len(ocr_text) > 500:
            print("...")

    except Exception as e:
        print(f"❌ OCR Error: {e}")
        import traceback
        traceback.print_exc()

    # Test 3: Full parser (barcode + OCR)
    print("\n" + "-" * 60)
    print("TEST 3: Full Parser (Barcode + OCR)")
    print("-" * 60)

    try:
        from ocr import extract_text
        from parser import parse_boarding_pass

        print("🔍 Running full parser...")
        ocr_text = extract_text(image_bytes)
        boarding_pass, confidence, warnings, quality = parse_boarding_pass(ocr_text, image_bytes)

        print(f"✅ Parsing completed\n")
        print(f"Overall Confidence: {confidence}")
        print(f"Quality: {quality}")
        print(f"Warnings: {len(warnings)}")

        if warnings:
            print("\nWarnings:")
            for warning in warnings[:5]:  # Show first 5
                print(f"  - {warning.field}: {warning.reason}")

        print(f"\nBarcode Present: {boarding_pass.barcode is not None}")
        if boarding_pass.barcode:
            print(f"Barcode Type: {boarding_pass.barcode.get('type', 'Unknown')}")

        print(f"\nPassenger: {boarding_pass.passenger.full_name.value if boarding_pass.passenger.full_name else 'N/A'}")
        print(f"PNR: {boarding_pass.pnr.value if boarding_pass.pnr else 'N/A'}")
        print(f"Segments: {len(boarding_pass.segments)}")

        for segment in boarding_pass.segments:
            print(f"\nSegment {segment.segment_number}:")
            print(f"  Route: {segment.route.origin.iata.value} → {segment.route.destination.iata.value}")
            print(f"  Flight: {segment.flight.airline_code.value}{segment.flight.flight_number.value}")
            print(f"  Date: {segment.schedule.departure_date.value if segment.schedule.departure_date else 'N/A'}")
            print(f"  Seat: {segment.boarding.seat.value if segment.boarding and segment.boarding.seat else 'N/A'}")

    except Exception as e:
        print(f"❌ Parser Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_barcode.py <path_to_boarding_pass_image>")
        print("\nExample:")
        print("  python test_barcode.py pnr_pass.jpg")
        sys.exit(1)

    image_path = sys.argv[1]
    test_barcode_extraction(image_path)
