# Authentication Testing Guide

## Quick Start

Your API now has Firebase Authentication with **dev mode** for easy testing!

---

## 🔧 Development Mode (Easy Testing)

### Step 1: Enable Dev Mode

Create `.env` file (or it's already created):
```bash
DEV_MODE=true
```

### Step 2: Start API

```bash
uvicorn main:app --reload
```

You should see:
```
🚀 Starting Travel Tracker API...
🔧 DEV_MODE: True
⚠️  WARNING: Development mode enabled - authentication can be bypassed!
🔧 Firebase initialized (DEV MODE enabled)
✅ API ready!
```

### Step 3: Test in Browser with Swagger UI

1. Open: http://localhost:8000/docs
2. Click any endpoint (e.g., "GET /trips")
3. Click "Try it out"
4. Click "Execute"
5. ✅ Works without authentication!

---

## 🎯 Testing Different Users

### Method 1: Default Test User

No auth needed - automatically uses `test_user_123`:

```bash
curl http://localhost:8000/trips
```

### Method 2: Custom User (Multi-User Testing)

Use `X-Dev-User-ID` header to impersonate any user:

```bash
# Test as Alice
curl -H "X-Dev-User-ID: alice" \
  -X POST http://localhost:8000/trips \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "DXB",
    "destination": "LAX",
    "title": "Alice's trip"
  }'

# Test as Bob
curl -H "X-Dev-User-ID: bob" \
  -X POST http://localhost:8000/trips \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "JFK",
    "destination": "LHR",
    "title": "Bob's trip"
  }'

# List Alice's trips (won't see Bob's)
curl -H "X-Dev-User-ID: alice" http://localhost:8000/trips

# List Bob's trips (won't see Alice's)
curl -H "X-Dev-User-ID: bob" http://localhost:8000/trips
```

### Method 3: Swagger UI with Custom User

1. Go to http://localhost:8000/docs
2. Click "Authorize" button (top right)
3. Leave token field empty
4. Click "Authorize" then "Close"
5. For each request, Swagger UI will let you add custom headers
6. Add header: `X-Dev-User-ID: your-user-id`

---

## 🔐 Production Mode (Real Auth)

### Step 1: Enable Production Mode

Update `.env`:
```bash
DEV_MODE=false
```

### Step 2: Generate Test Token (Python)

Create `generate_test_token.py`:
```python
from auth.firebase_auth import create_custom_token_for_testing

token = create_custom_token_for_testing("test_user_123")
print(f"Test Token: {token}")
```

Run:
```bash
python generate_test_token.py
```

### Step 3: Test with Token

```bash
TOKEN="<your-generated-token>"

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/trips
```

### Step 4: Swagger UI with Auth

1. Go to http://localhost:8000/docs
2. Click "Authorize" button
3. Enter: `<your-token>` (no "Bearer" prefix)
4. Click "Authorize" then "Close"
5. All requests now include auth!

---

## 📋 Complete Testing Examples

### Test Boarding Pass Extraction

```bash
# Dev mode - as specific user
curl -X POST \
  -H "X-Dev-User-ID: alice" \
  -F "file=@boarding_pass.jpg" \
  "http://localhost:8000/extract-boarding-pass?save_trip=true"

# Production mode - with token
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@boarding_pass.jpg" \
  "http://localhost:8000/extract-boarding-pass?save_trip=true"
```

### Test Manual Trip Creation

```bash
# Dev mode
curl -X POST http://localhost:8000/trips \
  -H "X-Dev-User-ID: alice" \
  -H "Content-Type: application/json" \
  -d '{
    "trip_type": "flight",
    "origin": "DXB",
    "destination": "IAH",
    "departure_date": "2026-02-14",
    "title": "Dubai to Houston",
    "notes": "Business trip"
  }'

# Production mode
curl -X POST http://localhost:8000/trips \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "trip_type": "flight",
    "origin": "DXB",
    "destination": "IAH",
    "departure_date": "2026-02-14"
  }'
```

### Test Trip Listing

```bash
# Dev mode - as Alice
curl -H "X-Dev-User-ID: alice" \
  "http://localhost:8000/trips?limit=10&offset=0"

# Production mode
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/trips?limit=10&offset=0"
```

### Test Trip Search

```bash
# Dev mode
curl -H "X-Dev-User-ID: alice" \
  "http://localhost:8000/trips/search?destination=DXB&airline=EK"

# Production mode
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/trips/search?destination=DXB"
```

### Test Trip Stats

```bash
# Dev mode
curl -H "X-Dev-User-ID: alice" \
  "http://localhost:8000/trips/stats"

# Production mode
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/trips/stats"
```

---

## 🧪 Testing Tools

### Option 1: Thunder Client (VS Code)

1. Install "Thunder Client" extension
2. Create new request
3. Set URL: `http://localhost:8000/trips`
4. Headers tab → Add:
   - **Dev mode**: `X-Dev-User-ID: alice`
   - **Production**: `Authorization: Bearer <token>`
5. Click "Send"
6. Save for reuse!

### Option 2: Postman

Same as Thunder Client but standalone app.

### Option 3: Python Test Script

```python
# test_api.py
import requests

BASE_URL = "http://localhost:8000"

# Dev mode - test as different users
def test_dev_mode():
    # Alice's trips
    headers = {"X-Dev-User-ID": "alice"}
    response = requests.get(f"{BASE_URL}/trips", headers=headers)
    print("Alice's trips:", response.json())

    # Bob's trips
    headers = {"X-Dev-User-ID": "bob"}
    response = requests.get(f"{BASE_URL}/trips", headers=headers)
    print("Bob's trips:", response.json())

# Production mode - test with token
def test_production_mode(token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/trips", headers=headers)
    print("Trips:", response.json())

if __name__ == "__main__":
    test_dev_mode()
```

---

## 🔍 Authentication Flow Summary

```
┌─────────────────────────────────────────────┐
│ DEV_MODE = true                             │
├─────────────────────────────────────────────┤
│ 1. No auth → test_user_123                  │
│ 2. X-Dev-User-ID header → custom user       │
│ 3. Bearer token → verify (optional)         │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ DEV_MODE = false (Production)               │
├─────────────────────────────────────────────┤
│ 1. No auth → 401 Unauthorized               │
│ 2. Invalid token → 401 Unauthorized         │
│ 3. Valid Bearer token → Extract user_id     │
└─────────────────────────────────────────────┘
```

---

## ⚠️ Important Notes

### Security
- **Never deploy with `DEV_MODE=true`** in production!
- Dev mode bypasses authentication - only for local testing
- Always use `DEV_MODE=false` for staging/production

### Multi-User Testing
- Each user_id gets isolated data in Firestore
- Alice can't see Bob's trips (even in dev mode)
- Perfect for testing multi-tenant scenarios

### Swagger UI
- Works in both dev and production mode
- Use "Authorize" button for token auth
- Add `X-Dev-User-ID` via custom headers in dev mode

---

## 🚀 Next Steps

1. ✅ **Test locally** with dev mode
2. ✅ **Test multi-user** scenarios
3. ✅ **Try Swagger UI** for interactive testing
4. 🔜 **Set up real Firebase** authentication for production
5. 🔜 **Build frontend** app with Firebase Auth SDK
6. 🔜 **Deploy** with `DEV_MODE=false`

---

## 📚 Additional Resources

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health
- **Firebase Auth Docs**: https://firebase.google.com/docs/auth

Happy testing! 🎉
