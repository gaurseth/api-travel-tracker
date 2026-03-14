# main.py
import os
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List
from dotenv import load_dotenv
import traceback

from ocr import extract_text
from parser import parse_boarding_pass
from extractors.bcbp_extractor import BCBPParser
from extractors.llm_extractor import extract_segments_from_image
from services import TripService
from auth import get_current_user, init_firebase

# Load environment variables from .env file
load_dotenv()


def is_dev_mode() -> bool:
    """Check if dev mode is enabled (dynamically)."""
    return os.getenv("is_dev_mode()", "false").lower() == "true"

# Initialize FastAPI with security scheme for Swagger UI
app = FastAPI(
    title="Travel Tracker API",
    description=f"""
Multi-user travel tracking API with boarding pass extraction and trip management.

**Authentication**: All endpoints (except / and /health) require authentication.

{'🔧 **DEV MODE ENABLED** - Authentication can be bypassed for testing.' if is_dev_mode() else '🔒 **Production Mode** - Valid Firebase token required.'}

## Authentication Methods

### Production Mode (is_dev_mode()=false)
- Requires valid Firebase JWT token
- Header: `Authorization: Bearer <firebase-token>`

### Development Mode (is_dev_mode()=true)
- **Option 1**: Use `X-Dev-User-ID` header to impersonate any user
- **Option 2**: No auth → defaults to `test_user_123`
- **Option 3**: Real Firebase token (for testing production-like auth)

## Dev Mode Testing Examples

```bash
# Test as specific user
curl -H "X-Dev-User-ID: alice" http://localhost:8000/trips

# Test as default user
curl http://localhost:8000/trips

# Test with real token
curl -H "Authorization: Bearer <token>" http://localhost:8000/trips
```
    """,
    version="1.0.0"
)

# Security scheme for Swagger UI
security = HTTPBearer(
    description="Firebase JWT token (or X-Dev-User-ID header in dev mode)"
)


# ============================================
# Startup Event - Initialize Firebase
# ============================================

@app.on_event("startup")
async def startup_event():
    """Initialize Firebase on application startup."""
    print("🚀 Starting Travel Tracker API...")
    print(f"🔧 is_dev_mode(): {is_dev_mode()}")

    if is_dev_mode():
        print("⚠️  WARNING: Development mode enabled - authentication can be bypassed!")
        print("   To enable production auth, set: is_dev_mode()=false")

    # Initialize Firebase Admin SDK
    init_firebase()
    print("✅ API ready!")


# ============================================
# Request/Response Models
# ============================================

class CreateManualTripRequest(BaseModel):
    """Request model for creating a manual trip."""
    tenant_id: str = "personal"
    trip_type: str = "flight"
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[str] = None
    arrival_date: Optional[str] = None
    airline_code: Optional[str] = None
    flight_number: Optional[str] = None
    passenger_name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class BoardingPassBarcodeRequest(BaseModel):
    """Request model for creating/attaching from a frontend-scanned BCBP string."""
    bcbp_string: str = Field(description="Raw IATA BCBP string from a PDF417 barcode scan")
    tenant_id: str = Field(default="personal")
    journey_type: str = Field(default="outward", description="'outward' or 'return'")


class ExtractFromScanRequest(BaseModel):
    """Request model for extraction-only barcode parsing (no trip creation)."""
    bcbp_string: str = Field(description="Raw IATA BCBP string from a PDF417 barcode scan")


class UpdateTripRequest(BaseModel):
    """Request model for updating a trip."""
    title: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[str] = None
    arrival_date: Optional[str] = None


class SegmentInput(BaseModel):
    """Request model for adding or updating a manual trip segment."""
    journey_type: str = Field(default="outward", description="'outward' or 'return'")
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[str] = None
    departure_time: Optional[str] = None
    arrival_date: Optional[str] = None
    arrival_time: Optional[str] = None
    airline_code: Optional[str] = None
    flight_number: Optional[str] = None
    seat: Optional[str] = None
    gate: Optional[str] = None
    boarding_time: Optional[str] = None
    notes: Optional[str] = None


# ============================================
# Public Endpoints (No Auth Required)
# ============================================

@app.get("/", tags=["Info"])
async def root():
    """API root with available endpoints."""
    return {
        "message": "Welcome to the Travel Tracker API!",
        "version": "1.0.0",
        "dev_mode": is_dev_mode(),
        "authentication": "optional" if is_dev_mode() else "required",
        "endpoints": {
            "POST /extract-from-image": "Extract segments from boarding pass image (auth required)",
            "POST /extract-from-scan": "Extract segments from BCBP barcode string (auth required)",
            "POST /process-boarding-pass": "Extract, merge, match & save trip from image + optional barcode (auth required)",
            "POST /trips": "Create manual trip (auth required)",
            "GET /trips": "List all trips for user (auth required)",
            "GET /trips/{trip_id}": "Get specific trip (auth required)",
            "PATCH /trips/{trip_id}": "Update trip (auth required)",
            "DELETE /trips/{trip_id}": "Delete trip (auth required)",
            "GET /trips/stats": "Get trip statistics (auth required)",
            "POST /trips/{trip_id}/attach-barcode": "Attach barcode segments to existing trip (auth required)",
            "POST /trips/{trip_id}/attach-boarding-pass": "Attach boarding pass image to existing trip (auth required)",
        },
        "docs": {
            "swagger": "/docs",
            "redoc": "/redoc"
        }
    }


@app.get("/health", tags=["Info"])
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "dev_mode": is_dev_mode()
    }


# ============================================
# Boarding Pass Extraction (Protected)
# ============================================

@app.post("/extract-from-image", tags=["Extraction"])
async def extract_from_image(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """
    Extract boarding pass data from an image (OCR). Returns segments without saving a trip.

    **Authentication Required**: User is automatically identified from auth token.

    Args:
        file: Boarding pass image file

    Returns:
        - segments: List of extracted segment dicts
        - passenger_name: Passenger name (if found)
        - pnr: PNR / booking reference (if found)
        - extraction_metadata: Confidence, quality, method
    """
    try:
        image_bytes = await file.read()
        raw_text = extract_text(image_bytes)

        boarding_pass, overall_confidence, warnings, quality_label = parse_boarding_pass(raw_text)

        segments = TripService.boarding_pass_to_segment_dicts(boarding_pass)
        passenger_name = (
            boarding_pass.passenger.full_name.value
            if boarding_pass.passenger.full_name else None
        )
        pnr = boarding_pass.pnr.value if boarding_pass.pnr else None

        return {
            "segments": segments,
            "passenger_name": passenger_name,
            "pnr": pnr,
            "extraction_metadata": {
                "overall_confidence": overall_confidence,
                "quality": quality_label,
                "warnings": [w.model_dump() for w in warnings] if warnings else [],
                "method": "ocr",
            },
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Barcode String Endpoints (Protected)
# ============================================

@app.post("/extract-from-scan", tags=["Extraction"])
async def extract_from_scan(
    request: ExtractFromScanRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Extract boarding pass data from a BCBP barcode string. Returns segments without saving a trip.

    **Authentication Required**: User is automatically identified from auth token.

    The frontend scans the PDF417 barcode and sends the raw BCBP string.

    Args:
        bcbp_string: Raw IATA BCBP string (must start with 'M')

    Returns:
        - segments: List of extracted segment dicts
        - passenger_name: Passenger name (if found)
        - pnr: PNR / booking reference (if found)
        - extraction_metadata: Method info
    """
    try:
        bcbp_data = BCBPParser.parse(request.bcbp_string)
        if not bcbp_data:
            raise HTTPException(status_code=422, detail="Invalid or unrecognised BCBP string")

        segments = TripService.bcbp_data_to_segment_dicts(bcbp_data)

        return {
            "segments": segments,
            "passenger_name": bcbp_data.get("passenger_name"),
            "pnr": bcbp_data.get("pnr"),
            "extraction_metadata": {
                "overall_confidence": 0.98,
                "quality": "excellent",
                "warnings": [],
                "method": "barcode_pdf417",
                "num_segments": bcbp_data.get("num_segments"),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Unified Process Endpoint (Protected)
# ============================================

@app.post("/process-boarding-pass", status_code=201, tags=["Boarding Pass"])
async def process_boarding_pass(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
    bcbp_string: Optional[str] = Query(default=None, description="Raw BCBP string from PDF417 barcode scan"),
    tenant_id: str = Query(default="personal", description="Tenant identifier"),
    journey_type: str = Query(default="outward", description="'outward' or 'return'"),
):
    """
    Unified boarding pass processing pipeline: extract, merge, match, and save.

    **Authentication Required**: User is automatically identified from auth token.

    Pipeline:
    1. EXTRACT — Parse barcode (if bcbp_string provided) and OCR (from image)
    2. MERGE — Combine barcode + OCR segments (barcode fields take priority)
    3. MATCH — Find existing trip that these segments belong to (by PNR, route, time)
    4. SAVE — Attach to matched trip or create a new one

    Args:
        file: Boarding pass image file (always required for OCR)
        bcbp_string: Optional raw BCBP string from frontend barcode scan
        tenant_id: Tenant identifier (default: "personal")
        journey_type: "outward" or "return" (default: "outward")

    Returns:
        - trip_id: ID of the created or matched trip
        - is_new_trip: Whether a new trip was created
        - match_score: Score of the match (if matched to existing trip)
        - segments: Merged segment dicts
        - extraction_metadata: Details about extraction sources
    """
    try:
        barcode_segments = []
        bcbp_data = None

        # 1. EXTRACT — barcode (if provided)
        if bcbp_string:
            bcbp_data = BCBPParser.parse(bcbp_string)
            if bcbp_data:
                barcode_segments = TripService.bcbp_data_to_segment_dicts(bcbp_data)
            else:
                print(f"Warning: BCBP parse failed, proceeding with OCR only")

        # 2. EXTRACT — OCR (always)
        image_bytes = await file.read()
        raw_text = extract_text(image_bytes)
        ocr_segments = []
        ocr_confidence = 0.0
        ocr_quality = "none"
        ocr_warnings = []

        try:
            boarding_pass, ocr_confidence, ocr_warnings, ocr_quality = parse_boarding_pass(raw_text)
            ocr_segments = TripService.boarding_pass_to_segment_dicts(boarding_pass)
        except Exception as ocr_err:
            print(f"Warning: OCR parse failed: {ocr_err}")

        # 2b. LLM FALLBACK — when OCR confidence is low
        llm_fallback_enabled = os.getenv("LLM_FALLBACK_ENABLED", "false").lower() == "true"
        llm_threshold = float(os.getenv("LLM_FALLBACK_THRESHOLD", "0.6"))
        used_llm = False

        if llm_fallback_enabled and ocr_confidence < llm_threshold:
            print(f"OCR confidence {ocr_confidence:.2f} < {llm_threshold}, triggering LLM fallback...")
            try:
                # Build barcode context to guide the LLM
                barcode_context = None
                if bcbp_data:
                    barcode_context = {
                        "num_segments": bcbp_data.get("num_segments"),
                        "passenger_name": bcbp_data.get("passenger_name"),
                        "pnr": bcbp_data.get("pnr"),
                        "segments": barcode_segments,
                    }

                llm_segments, llm_confidence = extract_segments_from_image(
                    image_bytes=image_bytes,
                    raw_ocr_text=raw_text,
                    barcode_context=barcode_context,
                )

                if llm_segments:
                    ocr_segments = llm_segments
                    ocr_confidence = llm_confidence
                    ocr_quality = "good"
                    ocr_warnings = []
                    used_llm = True
                    print(f"LLM fallback succeeded: {len(llm_segments)} segment(s), confidence {llm_confidence:.2f}")
                else:
                    print("LLM fallback returned no segments, keeping original OCR result")

            except Exception as llm_err:
                print(f"LLM fallback failed: {llm_err}, keeping original OCR result")

        # If both sources failed, return error
        if not barcode_segments and not ocr_segments:
            raise HTTPException(
                status_code=422,
                detail="Could not extract any segment data from image or barcode"
            )

        # 3. MERGE — barcode fields take priority, with guardrails
        merged_segments, merge_warnings = TripService._merge_segments(barcode_segments, ocr_segments)

        # Combine OCR parser warnings + merge guardrail warnings
        all_warnings = ([w.model_dump() for w in ocr_warnings] if ocr_warnings else []) + merge_warnings

        # Build extraction metadata
        if used_llm:
            method = "barcode_pdf417+llm_vision" if barcode_segments else "llm_vision"
        elif barcode_segments and ocr_segments:
            method = "barcode_pdf417+ocr"
        elif barcode_segments:
            method = "barcode_pdf417"
        else:
            method = "ocr"

        extraction_metadata = {
            "method": method,
            "overall_confidence": 0.98 if barcode_segments else ocr_confidence,
            "quality": "excellent" if barcode_segments else ocr_quality,
            "warnings": all_warnings,
            "barcode_parsed": bool(barcode_segments),
            "ocr_parsed": bool(ocr_segments),
            "num_segments": len(merged_segments),
        }

        # Derive passenger name / PNR from best source
        passenger_name = None
        pnr = None
        if bcbp_data:
            passenger_name = bcbp_data.get("passenger_name")
            pnr = bcbp_data.get("pnr")
        if not passenger_name and merged_segments:
            passenger_name = merged_segments[0].get("passenger_name")
        if not pnr and merged_segments:
            pnr = merged_segments[0].get("pnr")

        # 4. MATCH — find existing trip
        match_result = TripService.find_matching_trip(user_id, merged_segments)

        # 5. SAVE — attach or create
        if match_result:
            success = TripService.attach_segments_to_trip(
                user_id=user_id,
                trip_id=match_result["trip_id"],
                segments=merged_segments,
                journey_type=journey_type,
                extraction_metadata=extraction_metadata,
                raw_text=bcbp_string or raw_text,
            )
            if not success:
                # Trip disappeared between match and attach — create new
                match_result = None

        if match_result:
            return {
                "trip_id": match_result["trip_id"],
                "is_new_trip": False,
                "match_score": match_result["score"],
                "segments": merged_segments,
                "passenger_name": passenger_name,
                "pnr": pnr,
                "extraction_metadata": extraction_metadata,
            }
        else:
            trip_result = TripService.create_trip_from_segments(
                user_id=user_id,
                tenant_id=tenant_id,
                segments=merged_segments,
                journey_type=journey_type,
                passenger_name=passenger_name,
                extraction_metadata=extraction_metadata,
                raw_text=bcbp_string or raw_text,
            )
            return {
                "trip_id": trip_result["trip_id"],
                "is_new_trip": True,
                "match_score": None,
                "segments": merged_segments,
                "passenger_name": passenger_name,
                "pnr": pnr,
                "extraction_metadata": extraction_metadata,
            }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trips/{trip_id}/attach-barcode", tags=["Boarding Pass"])
async def attach_barcode_to_trip(
    trip_id: str,
    request: BoardingPassBarcodeRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Attach a frontend-scanned BCBP barcode as new segment(s) to an existing trip.

    **Authentication Required**: Only allows attaching to trips belonging to the authenticated user.

    Useful for adding a return leg or connecting flight to an existing trip.

    Args:
        trip_id: ID of the existing trip
        bcbp_string: Raw IATA BCBP string (must start with 'M')
        journey_type: "outward" or "return" — how to classify the new segments
    """
    try:
        bcbp_data = BCBPParser.parse(request.bcbp_string)
        if not bcbp_data:
            raise HTTPException(status_code=422, detail="Invalid or unrecognised BCBP string")

        segments = TripService.bcbp_data_to_segment_dicts(bcbp_data)

        extraction_metadata = {
            "overall_confidence": 0.98,
            "quality": "excellent",
            "method": "barcode_pdf417",
            "num_segments": bcbp_data.get("num_segments"),
        }

        success = TripService.attach_segments_to_trip(
            user_id=user_id,
            trip_id=trip_id,
            segments=segments,
            journey_type=request.journey_type,
            extraction_metadata=extraction_metadata,
            raw_text=request.bcbp_string,
        )

        if not success:
            raise HTTPException(status_code=404, detail="Trip not found")

        return {
            "message": "Barcode attached successfully",
            "trip_id": trip_id,
            "journey_type": request.journey_type,
            "extraction_metadata": extraction_metadata,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Trip Management Endpoints (Protected)
# ============================================

@app.post("/trips", status_code=201, tags=["Trips"])
async def create_manual_trip(
    request: CreateManualTripRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Create a new trip manually (without boarding pass).

    **Authentication Required**: User is automatically identified from auth token.

    Use this endpoint to create trips that don't have boarding passes yet,
    or for non-flight travel (train, bus, car, etc.).
    """
    try:
        result = TripService.create_manual_trip(
            user_id=user_id,
            tenant_id=request.tenant_id,
            trip_type=request.trip_type,
            origin=request.origin,
            destination=request.destination,
            departure_date=request.departure_date,
            arrival_date=request.arrival_date,
            airline_code=request.airline_code,
            flight_number=request.flight_number,
            passenger_name=request.passenger_name,
            title=request.title,
            description=request.description,
            notes=request.notes,
            tags=request.tags
        )

        return {
            "trip_id": result["trip_id"],
            "created_at": result["created_at"],
            "message": "Trip created successfully"
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trips", tags=["Trips"])
async def list_trips(
    user_id: str = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Results offset"),
    order_by: str = Query(default="created_at", description="Field to order by"),
    order_direction: str = Query(default="desc", regex="^(asc|desc)$")
):
    """
    List all trips for the authenticated user with pagination.

    **Authentication Required**: Only returns trips belonging to the authenticated user.
    """
    try:
        trips = TripService.list_trips(
            user_id=user_id,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_direction=order_direction
        )

        return {
            "trips": trips,
            "count": len(trips),
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trips/search", tags=["Trips"])
async def search_trips(
    user_id: str = Depends(get_current_user),
    destination: Optional[str] = Query(default=None, description="Destination filter"),
    origin: Optional[str] = Query(default=None, description="Origin filter"),
    airline: Optional[str] = Query(default=None, description="Airline code filter"),
    trip_type: Optional[str] = Query(default=None, description="Trip type filter"),
    start_date: Optional[str] = Query(default=None, description="Start date filter (ISO-8601)"),
    end_date: Optional[str] = Query(default=None, description="End date filter (ISO-8601)"),
    limit: int = Query(default=50, ge=1, le=100)
):
    """
    Search trips with filters for the authenticated user.

    **Authentication Required**: Only searches trips belonging to the authenticated user.
    """
    try:
        trips = TripService.search_trips(
            user_id=user_id,
            destination=destination,
            origin=origin,
            airline=airline,
            trip_type=trip_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )

        return {
            "trips": trips,
            "count": len(trips),
            "filters": {
                "destination": destination,
                "origin": origin,
                "airline": airline,
                "trip_type": trip_type,
                "start_date": start_date,
                "end_date": end_date
            }
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trips/stats", tags=["Trips"])
async def get_trip_stats(
    user_id: str = Depends(get_current_user)
):
    """
    Get statistics about the authenticated user's trips.

    **Authentication Required**: Returns stats for the authenticated user only.
    """
    try:
        stats = TripService.get_trip_stats(user_id=user_id)
        return stats

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trips/{trip_id}", tags=["Trips"])
async def get_trip(
    trip_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Get a specific trip by ID.

    **Authentication Required**: Only returns trip if it belongs to the authenticated user.
    """
    try:
        trip = TripService.get_trip(user_id=user_id, trip_id=trip_id)

        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found")

        return trip

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/trips/{trip_id}", tags=["Trips"])
async def update_trip(
    trip_id: str,
    request: UpdateTripRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Update a trip's details.

    **Authentication Required**: Only allows updating trips belonging to the authenticated user.
    """
    try:
        # Build updates dict from request
        updates = {}
        if request.title is not None:
            updates["title"] = request.title
        if request.description is not None:
            updates["description"] = request.description
        if request.notes is not None:
            updates["notes"] = request.notes
        if request.tags is not None:
            updates["tags"] = request.tags
        if request.origin is not None:
            updates["origin"] = request.origin
        if request.destination is not None:
            updates["destination"] = request.destination
        if request.departure_date is not None:
            updates["departure_date"] = request.departure_date
        if request.arrival_date is not None:
            updates["arrival_date"] = request.arrival_date

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        success = TripService.update_trip(
            user_id=user_id,
            trip_id=trip_id,
            updates=updates
        )

        if not success:
            raise HTTPException(status_code=404, detail="Trip not found")

        return {"message": "Trip updated successfully", "trip_id": trip_id}

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/trips/{trip_id}", tags=["Trips"])
async def delete_trip(
    trip_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Delete a trip.

    **Authentication Required**: Only allows deleting trips belonging to the authenticated user.
    """
    try:
        success = TripService.delete_trip(user_id=user_id, trip_id=trip_id)

        if not success:
            raise HTTPException(status_code=404, detail="Trip not found")

        return {"message": "Trip deleted successfully", "trip_id": trip_id}

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trips/{trip_id}/attach-boarding-pass", tags=["Trips"])
async def attach_boarding_pass(
    trip_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user)
):
    """
    Attach a scanned boarding pass to an existing manual trip.

    **Authentication Required**: Only allows attaching to trips belonging to the authenticated user.
    """
    try:
        # Extract and parse boarding pass
        image_bytes = await file.read()
        raw_text = extract_text(image_bytes)
        boarding_pass, overall_confidence, warnings, quality_label = parse_boarding_pass(raw_text)

        # Attach to trip
        success = TripService.attach_boarding_pass_to_trip(
            user_id=user_id,
            trip_id=trip_id,
            boarding_pass=boarding_pass,
            overall_confidence=overall_confidence,
            quality_label=quality_label,
            warnings=warnings,
            raw_text=raw_text,
            extraction_method="rules"
        )

        if not success:
            raise HTTPException(status_code=404, detail="Trip not found")

        return {
            "message": "Boarding pass attached successfully",
            "trip_id": trip_id,
            "extraction_metadata": {
                "overall_confidence": overall_confidence,
                "quality": quality_label,
                "warnings": warnings
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trips/{trip_id}/segments", tags=["Trips"])
async def add_segment(
    trip_id: str,
    request: SegmentInput,
    user_id: str = Depends(get_current_user)
):
    """
    Add a manually entered segment to an existing trip.

    Recomputes the trip-level derived fields (origin, destination, dates)
    from the updated outward segments after adding.
    """
    try:
        result = TripService.add_manual_segment(
            user_id=user_id,
            trip_id=trip_id,
            journey_type=request.journey_type,
            origin=request.origin,
            destination=request.destination,
            departure_date=request.departure_date,
            departure_time=request.departure_time,
            arrival_date=request.arrival_date,
            arrival_time=request.arrival_time,
            airline_code=request.airline_code,
            flight_number=request.flight_number,
            seat=request.seat,
            gate=request.gate,
            boarding_time=request.boarding_time,
            notes=request.notes,
        )

        if result is None:
            raise HTTPException(status_code=404, detail="Trip not found")

        return {
            "message": "Segment added successfully",
            "trip_id": trip_id,
            "segment_number": result["segment_number"],
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/trips/{trip_id}/segments/{segment_number}", tags=["Trips"])
async def update_segment(
    trip_id: str,
    segment_number: int,
    request: SegmentInput,
    user_id: str = Depends(get_current_user)
):
    """
    Update an existing manual segment within a trip.

    Recomputes the trip-level derived fields after updating.
    """
    try:
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        success = TripService.update_manual_segment(
            user_id=user_id,
            trip_id=trip_id,
            segment_number=segment_number,
            **updates,
        )

        if not success:
            raise HTTPException(status_code=404, detail="Trip or segment not found")

        return {"message": "Segment updated successfully", "trip_id": trip_id}

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
