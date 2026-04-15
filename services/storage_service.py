"""
Cloud Storage service for boarding pass image storage.

Uploads images to Google Cloud Storage and generates signed URLs
for secure, time-limited frontend access.
"""
import io
import os
from datetime import timedelta
from typing import Optional

import cv2
import google.auth
import google.auth.transport.requests
import numpy as np
from PIL import Image
from google.cloud import storage

_client = None
_bucket = None

# GCS bucket name – set GCS_BUCKET_NAME env var to override
_BUCKET_NAME = os.getenv(
    "GCS_BUCKET_NAME",
    f"{os.getenv('GOOGLE_CLOUD_PROJECT', 'travel-tracker-9674d')}.appspot.com"
)

_SIGNED_URL_EXPIRY = timedelta(minutes=15)


def _get_bucket():
    """Lazy-init Cloud Storage bucket."""
    global _client, _bucket
    if _bucket is None:
        _client = storage.Client()
        _bucket = _client.bucket(_BUCKET_NAME)
    return _bucket


_MAX_DIMENSION = 1600  # max width or height in pixels
_JPEG_QUALITY = 70     # JPEG compression quality (1-100)
_MIN_CROP_RATIO = 0.25  # crop must be at least 25% of original area


def _auto_crop(img: Image.Image) -> Image.Image:
    """
    Detect the boarding pass rectangle and crop out surrounding background.
    Falls back to the original image if no clear document boundary is found.
    """
    orig_w, orig_h = img.size
    orig_area = orig_w * orig_h

    # Convert PIL → OpenCV (RGB → BGR)
    cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    # Grayscale → blur → edge detection
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    # Dilate edges to close gaps in the document border
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    edges = cv2.dilate(edges, kernel, iterations=2)

    # Find contours and pick the largest one that looks like a rectangle
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best_box = None
    best_area = 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < orig_area * _MIN_CROP_RATIO:
            continue

        # Approximate contour to a polygon
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        # Accept quadrilaterals (boarding pass shape)
        if 4 <= len(approx) <= 6 and area > best_area:
            best_area = area
            best_box = cv2.boundingRect(approx)

    if best_box is None:
        return img

    x, y, w, h = best_box

    # Add a small padding (2%) so we don't clip text at the edges
    pad_x = int(w * 0.02)
    pad_y = int(h * 0.02)
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(orig_w, x + w + pad_x)
    y2 = min(orig_h, y + h + pad_y)

    return img.crop((x1, y1, x2, y2))


def compress_image(image_bytes: bytes) -> bytes:
    """
    Auto-crop background, resize, and compress to JPEG.
    """
    img = Image.open(io.BytesIO(image_bytes))

    # Convert to RGB (strips alpha from PNG, handles CMYK, etc.)
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Detect and crop to the boarding pass boundary
    img = _auto_crop(img)

    # Resize if either dimension exceeds the limit
    w, h = img.size
    if w > _MAX_DIMENSION or h > _MAX_DIMENSION:
        img.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return buf.getvalue()


def upload_boarding_pass_image(
    user_id: str,
    boarding_pass_id: str,
    image_bytes: bytes,
) -> str:
    """
    Compress and upload a boarding pass image to Cloud Storage.

    Path: boarding-passes/{user_id}/{boarding_pass_id}.jpg

    Returns the GCS object path (not a URL).
    """
    compressed = compress_image(image_bytes)
    blob_path = f"boarding-passes/{user_id}/{boarding_pass_id}.jpg"

    bucket = _get_bucket()
    blob = bucket.blob(blob_path)
    blob.upload_from_string(compressed, content_type="image/jpeg")

    return blob_path


def get_signed_url(blob_path: str) -> Optional[str]:
    """
    Generate a signed URL for a stored image.

    Returns a time-limited (15 min) URL the frontend can use directly,
    or None if the blob doesn't exist.
    """
    bucket = _get_bucket()
    blob = bucket.blob(blob_path)

    if not blob.exists():
        return None

    # On Compute Engine / Cloud Run the default credentials don't carry a
    # private key, so we pass service_account_email + access_token to make
    # the library use the IAM signBlob API instead of local signing.
    credentials, _ = google.auth.default()
    signing_kwargs = {}
    if hasattr(credentials, "service_account_email"):
        credentials.refresh(google.auth.transport.requests.Request())
        signing_kwargs["service_account_email"] = credentials.service_account_email
        signing_kwargs["access_token"] = credentials.token

    url = blob.generate_signed_url(
        version="v4",
        expiration=_SIGNED_URL_EXPIRY,
        method="GET",
        **signing_kwargs,
    )
    return url


def delete_boarding_pass_images(user_id: str, boarding_pass_ids: list) -> None:
    """
    Delete images for the given boarding pass IDs.
    Silently skips any that don't exist.
    """
    bucket = _get_bucket()
    for bp_id in boarding_pass_ids:
        blob = bucket.blob(f"boarding-passes/{user_id}/{bp_id}.jpg")
        if blob.exists():
            blob.delete()


def delete_all_user_images(user_id: str) -> int:
    """
    Delete ALL boarding pass images for a user.
    Lists all blobs under boarding-passes/{user_id}/ and deletes them.

    Returns the number of blobs deleted.
    """
    bucket = _get_bucket()
    prefix = f"boarding-passes/{user_id}/"
    blobs = list(bucket.list_blobs(prefix=prefix))
    count = 0
    for blob in blobs:
        blob.delete()
        count += 1
    print(f"[Storage] Deleted {count} images for user {user_id}")
    return count
