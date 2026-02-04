# ocr.py
from google.cloud import vision

client = vision.ImageAnnotatorClient()

def extract_text(image_bytes):
    image = vision.Image(content=image_bytes)
    response = client.text_detection(image=image)

    texts = response.text_annotations
    if not texts:
        return ""

    return texts[0].description
    if response.error.message:
        raise Exception(f'Error during text detection: {response.error.message}')