# Complete Deployment Guide
## Deploy to travel-tracker-9674d and Set Up Local Development

---

## Overview

This guide will help you:
1. ✅ Deploy your backend to `travel-tracker-9674d` (same as Firebase)
2. ✅ Download credentials for local development
3. ✅ Test locally with dev mode
4. ✅ Test production deployment

---

## Prerequisites

- ✅ Google Cloud SDK (`gcloud`) installed
- ✅ Authenticated with Google Cloud
- ✅ Code pushed to GitHub (already done!)

---

## Part 1: Deploy to Cloud Run

### **Option A: Automated Deployment (Recommended)**

```bash
# Make deployment script executable
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

This will:
1. Set project to `travel-tracker-9674d`
2. Enable required APIs
3. Build and deploy to Cloud Run
4. Show you the service URL

### **Option B: Manual Deployment**

```bash
# 1. Set project
gcloud config set project travel-tracker-9674d

# 2. Enable APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  firestore.googleapis.com \
  vision.googleapis.com

# 3. Deploy
gcloud run deploy travel-tracker-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars DEV_MODE=false \
  --memory 512Mi \
  --project=travel-tracker-9674d
```

### **Expected Output**

```
Deploying container to Cloud Run service [travel-tracker-api]
✓ Creating Revision...
✓ Routing traffic...
Done.
Service [travel-tracker-api] revision [travel-tracker-api-00001] has been deployed
Service URL: https://travel-tracker-api-xxxx-uc.a.run.app
```

**Save this URL!** This is your production API endpoint.

---

## Part 2: Download Credentials for Local Development

### **Step 1: Go to Firebase Console**

```
https://console.firebase.google.com/project/travel-tracker-9674d/settings/serviceaccounts
```

### **Step 2: Generate Private Key**

1. Click **"Generate New Private Key"**
2. Click **"Generate Key"** in the popup
3. Download will start automatically
4. File name will be like: `travel-tracker-9674d-firebase-adminsdk-xxxxx.json`

### **Step 3: Move and Secure the Key**

```bash
# Create config directory
mkdir -p ~/.config/gcloud

# Move downloaded key (adjust filename)
mv ~/Downloads/travel-tracker-9674d-*.json ~/.config/gcloud/travel-tracker-key.json

# Secure it (only you can read)
chmod 600 ~/.config/gcloud/travel-tracker-key.json
```

### **Step 4: Set Environment Variable**

```bash
# Set for current session
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/gcloud/travel-tracker-key.json"

# Make it permanent (add to shell profile)
echo 'export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/gcloud/travel-tracker-key.json"' >> ~/.zshrc

# Reload shell
source ~/.zshrc
```

### **Step 5: Verify Credentials**

```bash
python3 check.py
```

**Expected output:**
```
✅ All checks passed!

  Your backend will connect to:
  📦 Firebase Project: travel-tracker-9674d

  Authentication Mode: 🔧 Development (optional)
```

---

## Part 3: Test Locally

### **Step 1: Start API**

```bash
uvicorn main:app --reload
```

**Expected output:**
```
🚀 Starting Travel Tracker API...
🔧 DEV_MODE: True
⚠️  WARNING: Development mode enabled - authentication can be bypassed!
🔧 Firebase initialized (DEV MODE enabled)
✅ API ready!
```

### **Step 2: Test Health Endpoint**

```bash
curl http://localhost:8000/health
```

**Expected:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "dev_mode": true
}
```

### **Step 3: Test Swagger UI**

Open in browser:
```
http://localhost:8000/docs
```

You should see all your endpoints!

### **Step 4: Test Trip Creation (Dev Mode)**

```bash
curl -X POST http://localhost:8000/trips \
  -H "X-Dev-User-ID: test_user" \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "DXB",
    "destination": "JFK",
    "departure_date": "2026-03-15",
    "title": "Test Trip"
  }'
```

**Expected:**
```json
{
  "trip_id": "trip_xxxxxxxxxxxx",
  "created_at": "2026-02-10T...",
  "message": "Trip created successfully"
}
```

### **Step 5: List Trips**

```bash
curl -H "X-Dev-User-ID: test_user" http://localhost:8000/trips
```

**Expected:**
```json
{
  "trips": [
    {
      "trip_id": "trip_xxxxxxxxxxxx",
      "origin": "DXB",
      "destination": "JFK",
      ...
    }
  ],
  "count": 1
}
```

---

## Part 4: Test Production Deployment

### **Step 1: Get Your Service URL**

```bash
gcloud run services describe travel-tracker-api \
  --platform managed \
  --region us-central1 \
  --format 'value(status.url)' \
  --project=travel-tracker-9674d
```

**Or check the deployment output from earlier.**

### **Step 2: Test Health Endpoint**

```bash
# Replace with your actual URL
SERVICE_URL="https://travel-tracker-api-xxxx-uc.a.run.app"

curl $SERVICE_URL/health
```

**Expected:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "dev_mode": false  ← Note: false in production!
}
```

### **Step 3: Test Swagger UI**

Open in browser:
```
https://travel-tracker-api-xxxx-uc.a.run.app/docs
```

### **Step 4: Test with Real Firebase Token**

Since production mode requires authentication, you'll need a real Firebase token:

```bash
# This will fail (no auth)
curl $SERVICE_URL/trips

# Returns: {"detail": "Missing Authorization header..."}
```

**To test with auth:**
1. Have your frontend app get a user token
2. Use that token:
```bash
curl -H "Authorization: Bearer <firebase-token>" $SERVICE_URL/trips
```

---

## Part 5: Firestore Database Setup

### **Step 1: Create Firestore Database**

If you haven't already:

```
https://console.firebase.google.com/project/travel-tracker-9674d/firestore
```

Click **"Create Database"**:
- Choose **Native Mode**
- Select region: `us-central1` (or same as Cloud Run)
- Start in **Production mode**

### **Step 2: Set Security Rules**

Go to: Firestore → Rules

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Allow authenticated users to access their own trips
    match /users/{userId}/trips/{tripId} {
      allow read, write: if request.auth != null
                         && request.auth.uid == userId;
    }
  }
}
```

Click **"Publish"**

---

## Troubleshooting

### **Issue: "GOOGLE_APPLICATION_CREDENTIALS not set"**

**Solution:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/gcloud/travel-tracker-key.json"
```

### **Issue: "Firebase initialization failed"**

**Solution:**
1. Run `python3 check.py` to diagnose
2. Make sure credentials file exists
3. Check project ID in credentials matches `travel-tracker-9674d`

### **Issue: "Missing Authorization header" in dev mode**

**Solution:**
1. Check `.env` file has `DEV_MODE=true`
2. Restart the server
3. Verify with: `curl http://localhost:8000/health`

### **Issue: Cloud Run deployment fails**

**Solution:**
```bash
# Check project is set correctly
gcloud config get-value project

# Should output: travel-tracker-9674d

# If wrong, set it:
gcloud config set project travel-tracker-9674d
```

---

## Summary Checklist

After completing this guide, you should have:

- ✅ Backend deployed to Cloud Run in `travel-tracker-9674d`
- ✅ Service URL saved
- ✅ Credentials downloaded and set up locally
- ✅ Local development working with dev mode
- ✅ Firestore database created
- ✅ Security rules set
- ✅ Both local and production tested

---

## Next Steps

1. **Connect your frontend** to the production API URL
2. **Test end-to-end** with real Firebase authentication
3. **Monitor logs**: `gcloud run logs read travel-tracker-api --project=travel-tracker-9674d`
4. **Set up CI/CD** for automatic deployments (optional)

---

## Quick Reference

**Local Development:**
```bash
# Check credentials
python3 check.py

# Start API
uvicorn main:app --reload

# Test
curl http://localhost:8000/health
```

**Production:**
```bash
# Deploy
./deploy.sh

# View logs
gcloud run logs read travel-tracker-api --project=travel-tracker-9674d

# Get URL
gcloud run services describe travel-tracker-api \
  --platform managed \
  --region us-central1 \
  --format 'value(status.url)' \
  --project=travel-tracker-9674d
```

---

🎉 **You're all set!** Your backend is now deployed to the same project as Firebase, making token verification seamless!
