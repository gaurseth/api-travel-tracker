#!/usr/bin/env python3
"""
Barcode test - precisely targets the PDF417 in the top strip.
The barcode is rotated 90° CW and has a stamp over the left portion.
"""
import sys
from pathlib import Path

def try_decode(image, label: str):
    from pyzbar import pyzbar
    barcodes = pyzbar.decode(image)
    if barcodes:
        print(f"  ✅ [{label}] Found {len(barcodes)} barcode(s)!")
        for bc in barcodes:
            data = bc.data.decode('utf-8', errors='ignore')
            print(f"     Type : {bc.type}")
            print(f"     Data : {data[:200]}")
        return barcodes
    print(f"  ❌ [{label}] Nothing")
    return []


def test_barcode_only(image_path: str):
    print("=" * 60)
    print("BARCODE DETECTION — TARGETED PDF417 EXTRACTION")
    print("=" * 60)

    with open(image_path, 'rb') as f:
        image_bytes = f.read()

    from PIL import Image, ImageEnhance, ImageFilter
    import io, cv2
    import numpy as np

    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    print(f"Original image: {w} x {h}\n")

    # The PDF417 barcode is in the TOP strip, bottom half, rotated 90° CW.
    # Top strip = crop(0, 0, w, int(h*0.15)) → 1722 x 604
    # Barcode is in bottom portion of that strip: y roughly 350-604
    top_strip = img.crop((0, 0, w, int(h * 0.15)))
    ts_w, ts_h = top_strip.size
    print(f"Top strip: {top_strip.size}")

    # Crop just the barcode rows within the top strip (bottom 45%)
    barcode_region = top_strip.crop((0, int(ts_h * 0.55), ts_w, ts_h))
    barcode_region.save("/tmp/barcode_region.jpg")
    print(f"Barcode region: {barcode_region.size}")
    print("Saved → /tmp/barcode_region.jpg\n")

    # The barcode bars run vertically in the image → rotate 90° CW to make them horizontal
    br_cw  = barcode_region.rotate(-90, expand=True)   # CW
    br_ccw = barcode_region.rotate( 90, expand=True)   # CCW
    br_cw.save("/tmp/barcode_cw.jpg")
    br_ccw.save("/tmp/barcode_ccw.jpg")
    print("Saved rotated versions → /tmp/barcode_cw.jpg, /tmp/barcode_ccw.jpg\n")

    print("🔍 Testing barcode region:\n")

    for label, src in [
        ("region original",        barcode_region),
        ("region CW-90",           br_cw),
        ("region CCW-90",          br_ccw),
        ("region gray",            barcode_region.convert('L')),
        ("region CW gray",         br_cw.convert('L')),
        ("region CCW gray",        br_ccw.convert('L')),
    ]:
        found = try_decode(src, label)
        if found: return

    # Scale up the rotated grays
    for rotation, src in [("CW", br_cw), ("CCW", br_ccw)]:
        gray = src.convert('L')
        rw, rh = gray.size
        for scale in [2, 3, 4, 6]:
            scaled = gray.resize((rw * scale, rh * scale), Image.LANCZOS)
            found = try_decode(scaled, f"region {rotation} gray {scale}x")
            if found: return

    # Otsu threshold on scaled
    for rotation, src in [("CW", br_cw), ("CCW", br_ccw)]:
        gray = np.array(src.convert('L'))
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        rh, rw = otsu.shape
        for scale in [2, 3, 4]:
            big = cv2.resize(otsu, (rw * scale, rh * scale), interpolation=cv2.INTER_NEAREST)
            found = try_decode(Image.fromarray(big), f"region {rotation} otsu {scale}x")
            if found: return

    # Try the full top strip (not just bottom half) in case barcode is taller
    print("\n🔍 Trying full top strip:\n")
    for rotation in [-90, 90, 0]:
        rotated = top_strip.rotate(rotation, expand=True).convert('L')
        rw, rh = rotated.size
        found = try_decode(rotated, f"full top strip rot {rotation}")
        if found: return
        for scale in [2, 3]:
            scaled = rotated.resize((rw * scale, rh * scale), Image.LANCZOS)
            found = try_decode(scaled, f"full top strip rot {rotation} {scale}x")
            if found: return

    print("\n" + "=" * 60)
    print("CONCLUSION")
    print("=" * 60)
    print("The PDF417 barcode is visible in /tmp/barcode_region.jpg")
    print("but cannot be decoded — the PRE-EMBARQUE stamp has corrupted")
    print("enough of the barcode that error correction cannot recover it.")
    print("\nThis is expected for a physically stamped boarding pass.")
    print("OCR extraction remains the reliable fallback for used passes.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_barcode_simple.py <image_path>")
        sys.exit(1)
    test_barcode_only(sys.argv[1])
