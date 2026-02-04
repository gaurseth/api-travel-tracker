from fastapi import FastAPI, File, UploadFile
from ocr import extract_text
from parser import parse_boarding_pass

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Welcome to the Boarding Pass OCR API!"}

@app.get("/extract-boarding-pass")
async def extract_boarding_pass(file: UploadFile = File()):
    image_bytes = await file.read()
    raw_text = extract_text(image_bytes)
    parsed_data = parse_boarding_pass(raw_text)

    return {
        "parsed_data": parsed_data,
        "raw_text": raw_text
    }
