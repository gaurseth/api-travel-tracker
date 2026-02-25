# main.py
import os
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
from dotenv import load_dotenv
import traceback

from ocr import extract_text
from parser import parse_boarding_pass
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
            "POST /extract-boarding-pass": "Extract boarding pass and create trip (auth required)",
            "POST /trips": "Create manual trip (auth required)",
            "GET /trips": "List all trips for user (auth required)",
            "GET /trips/{trip_id}": "Get specific trip (auth required)",
            "PATCH /trips/{trip_id}": "Update trip (auth required)",
            "DELETE /trips/{trip_id}": "Delete trip (auth required)",
            "GET /trips/stats": "Get trip statistics (auth required)",
            "POST /trips/{trip_id}/attach-boarding-pass": "Attach boarding pass to trip (auth required)"
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

@app.post("/extract-boarding-pass", tags=["Boarding Pass"])
async def extract_boarding_pass(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
    tenant_id: str = Query(default="personal", description="Tenant identifier"),
    save_trip: bool = Query(default=True, description="Save as trip in database")
):
    """
    Extract structured data from a boarding pass image and optionally save as a trip.

    **Authentication Required**: User is automatically identified from auth token.

    Args:
        file: Boarding pass image file
        tenant_id: Tenant identifier (default: "personal")
        save_trip: Whether to save extracted data as a trip (default: True)

    Returns:
        - trip_id: Trip ID (if saved)
        - boarding_pass: Structured boarding pass data
        - extraction_metadata: Confidence scores and warnings
        - raw_text: Raw OCR text for debugging
    """
    try:
        # Extract text from image
        image_bytes = await file.read()
        raw_text = extract_text(image_bytes)

        # Parse boarding pass with confidence scoring (tries barcode first, then OCR)
        boarding_pass, overall_confidence, warnings, quality_label = parse_boarding_pass(raw_text, image_bytes)

        response = {
            "boarding_pass": boarding_pass,
            "extraction_metadata": {
                "overall_confidence": overall_confidence,
                "quality": quality_label,
                "warnings": warnings,
                "method": "rules",
            },
            "raw_text": raw_text
        }

        # Save as trip if requested
        if save_trip:
            trip_result = TripService.create_trip_from_boarding_pass(
                user_id=user_id,
                tenant_id=tenant_id,
                boarding_pass=boarding_pass,
                overall_confidence=overall_confidence,
                quality_label=quality_label,
                warnings=warnings,
                raw_text=raw_text,
                extraction_method="rules"
            )
            response["trip_id"] = trip_result["trip_id"]
            response["trip_created_at"] = trip_result["created_at"]
            response["saved"] = True
        else:
            response["saved"] = False

        return response

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
        boarding_pass, overall_confidence, warnings, quality_label = parse_boarding_pass(raw_text, image_bytes)

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
