# ocr.py
from google.cloud import vision

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = vision.ImageAnnotatorClient()
    return _client

def extract_text(image_bytes):
    image = vision.Image(content=image_bytes)
    response = _get_client().text_detection(image=image)

    if response.error.message:
        raise Exception(f'Error during text detection: {response.error.message}')

    texts = response.text_annotations
    if not texts:
        return ""

    return texts[0].description