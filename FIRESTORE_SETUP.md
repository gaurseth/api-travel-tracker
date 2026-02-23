# Firestore Setup Guide

## Overview

Your Travel Tracker API now has full Firestore integration with:
- ✅ Trip persistence (with or without boarding passes)
- ✅ User isolation (multi-tenant architecture)
- ✅ Full CRUD operations
- ✅ Search and filtering
- ✅ Trip statistics

---

## Step 1: Set Up Google Cloud Firestore

### Option A: Using Existing GCP Project (Recommended)

Since you're already using Google Cloud Vision API, you likely have a GCP project set up.

1. **Enable Firestore API**
   ```bash
   gcloud services enable firestore.googleapis.com
   ```

2. **Create Firestore Database**
   - Go to: https://console.cloud.google.com/firestore
   - Click "Create Database"
   - Choose **Native Mode** (not Datastore mode)
   - Select region (choose same as your Cloud Run region)
   - Start in **Production mode**

### Option B: New GCP Project

```bash
# Create new project
gcloud projects create travel-tracker-prod

# Set project
gcloud config set project travel-tracker-prod

# Enable APIs
gcloud services enable firestore.googleapis.com
gcloud services enable vision.googleapis.com
```

---

## Step 2: Set Up Authentication

### For Local Development

1. **Create Service Account**
   ```bash
   gcloud iam service-accounts create travel-tracker-dev \
     --display-name="Travel Tracker Dev Service Account"
   ```

2. **Grant Permissions**
   ```bash
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:travel-tracker-dev@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/datastore.user"

   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:travel-tracker-dev@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/cloudfunctions.invoker"
   ```

3. **Download Credentials**
   ```bash
   gcloud iam service-accounts keys create ~/travel-tracker-key.json \
     --iam-account=travel-tracker-dev@YOUR_PROJECT_ID.iam.gserviceaccount.com
   ```

4. **Set Environment Variable**
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS=~/travel-tracker-key.json
   ```

   Add to your `~/.bashrc` or `~/.zshrc`:
   ```bash
   echo 'export GOOGLE_APPLICATION_CREDENTIALS=~/travel-tracker-key.json' >> ~/.bashrc
   source ~/.bashrc
   ```

### For Cloud Run Deployment

Cloud Run automatically provides credentials - no setup needed! 🎉

Just ensure your Cloud Run service has the Firestore User role:
```bash
gcloud run services add-iam-policy-binding travel-tracker-api \
  --region=YOUR_REGION \
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/datastore.user"
```

---

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

Or install directly:
```bash
pip install google-cloud-firestore
```

---

## Step 4: Firestore Data Structure

Your data is organized as:

```
users/
  {user_id}/
    trips/
      {trip_id}/
        - trip_id: string
        - user_id: string
        - tenant_id: string
        - trip_type: string
        - origin: string
        - destination: string
        - departure_date: string
        - boarding_pass: object (optional)
        - boarding_pass_attached: boolean
        - extraction_metadata: object
        - title: string
        - notes: string
        - tags: array
        - created_at: timestamp
        - updated_at: timestamp
```

### Why This Structure?

✅ **User isolation**: Each user's data is in their own subcollection
✅ **Fast queries**: Easy to list all trips for a user
✅ **Security**: Firestore rules can enforce user access
✅ **Scalable**: Grows with user base

---

## Step 5: Test the API

### 1. Start the Server

```bash
uvicorn main:app --reload --port 8000
```

### 2. Test Boarding Pass Extraction + Save

```bash
curl -X POST "http://localhost:8000/extract-boarding-pass?user_id=test_user_123&save_trip=true" \
  -F "file=@boarding_pass.jpg"
```

**Response:**
```json
{
  "trip_id": "trip_a1b2c3d4e5f6g7h8",
  "boarding_pass": { ... },
  "extraction_metadata": {
    "overall_confidence": 0.91,
    "quality": "excellent",
    "warnings": []
  },
  "saved": true
}
```

### 3. Create Manual Trip

```bash
curl -X POST "http://localhost:8000/trips" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user_123",
    "trip_type": "flight",
    "origin": "DXB",
    "destination": "IAH",
    "departure_date": "2026-02-14",
    "title": "Trip to Houston",
    "notes": "Business trip"
  }'
```

### 4. List All Trips

```bash
curl "http://localhost:8000/trips?user_id=test_user_123"
```

### 5. Get Trip Statistics

```bash
curl "http://localhost:8000/trips/stats?user_id=test_user_123"
```

**Response:**
```json
{
  "total_trips": 5,
  "total_flights": 5,
  "trip_types": {
    "flight": 5
  },
  "airlines": ["EK", "UA", "AA"],
  "destinations": ["DXB", "IAH", "JFK"],
  "origins": ["IAH", "JFK", "LHR"],
  "unique_routes": 4
}
```

### 6. Search Trips

```bash
curl "http://localhost:8000/trips/search?user_id=test_user_123&destination=DXB&airline=EK"
```

### 7. Update Trip

```bash
curl -X PATCH "http://localhost:8000/trips/trip_abc123?user_id=test_user_123" \
  -H "Content-Type: application/json" \
  -d '{
    "notes": "Updated notes",
    "tags": ["business", "emirates"]
  }'
```

### 8. Delete Trip

```bash
curl -X DELETE "http://localhost:8000/trips/trip_abc123?user_id=test_user_123"
```

---

## Step 6: Firestore Security Rules (Important!)

Create security rules to protect user data:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Users can only access their own trips
    match /users/{userId}/trips/{tripId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }

    // For now, allow authenticated access (you'll add proper auth later)
    match /users/{userId}/trips/{tripId} {
      allow read, write: if true; // TEMPORARY - CHANGE THIS!
    }
  }
}
```

**⚠️ IMPORTANT**: The temporary rule above allows ALL access. This is OK for development, but you MUST add proper authentication before production!

Apply rules via Firebase Console:
1. Go to Firestore → Rules
2. Paste the rules above
3. Publish

---

## Step 7: Create Firestore Indexes (For Search)

Some queries require indexes. Create them via:

1. **Via Console** (Easier):
   - Run a search query
   - Firestore will prompt you to create an index
   - Click the provided link

2. **Via CLI**:
   Create `firestore.indexes.json`:
   ```json
   {
     "indexes": [
       {
         "collectionGroup": "trips",
         "queryScope": "COLLECTION",
         "fields": [
           { "fieldPath": "user_id", "order": "ASCENDING" },
           { "fieldPath": "departure_date", "order": "DESCENDING" }
         ]
       },
       {
         "collectionGroup": "trips",
         "queryScope": "COLLECTION",
         "fields": [
           { "fieldPath": "user_id", "order": "ASCENDING" },
           { "fieldPath": "destination", "order": "ASCENDING" },
           { "fieldPath": "created_at", "order": "DESCENDING" }
         ]
       }
     ]
   }
   ```

   Deploy:
   ```bash
   firebase deploy --only firestore:indexes
   ```

---

## Step 8: Monitor Your Database

### View Data in Console
https://console.cloud.google.com/firestore/data

### Check Usage
```bash
gcloud firestore operations list
```

### Pricing Overview
- **Free tier**: 1GB storage, 50k reads/day, 20k writes/day, 20k deletes/day
- **Paid**: $0.18/GB storage, $0.06 per 100k reads, $0.18 per 100k writes

For a typical travel tracker user:
- ~50 trips/year = negligible cost
- Well within free tier for most users

---

## API Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/extract-boarding-pass` | Scan boarding pass & create trip |
| POST | `/trips` | Create manual trip |
| GET | `/trips` | List all trips |
| GET | `/trips/search` | Search trips with filters |
| GET | `/trips/stats` | Get trip statistics |
| GET | `/trips/{trip_id}` | Get specific trip |
| PATCH | `/trips/{trip_id}` | Update trip |
| DELETE | `/trips/{trip_id}` | Delete trip |
| POST | `/trips/{trip_id}/attach-boarding-pass` | Attach boarding pass to trip |

---

## Troubleshooting

### Error: "Could not load the default credentials"

**Solution**: Set `GOOGLE_APPLICATION_CREDENTIALS`:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

### Error: "PERMISSION_DENIED"

**Solutions**:
1. Check Firestore rules (Step 6)
2. Verify service account has `datastore.user` role
3. Ensure Firestore API is enabled

### Error: "The query requires an index"

**Solution**:
1. Click the provided link in the error
2. Or create indexes manually (Step 7)

---

## Next Steps

Now that Firestore is working:

1. ✅ **Add Authentication** - Implement JWT/OAuth (user_id should come from auth token)
2. ✅ **Add AI Fallback** - Improve extraction accuracy
3. ✅ **Add Image Quality Checks** - Pre-OCR validation
4. ✅ **Build Frontend** - React/Flutter app
5. ✅ **Deploy to Production** - Cloud Run deployment

---

## FastAPI Auto-Documentation

Your API now has interactive documentation:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

Try the endpoints directly from the browser! 🚀
