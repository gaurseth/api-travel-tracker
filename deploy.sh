#!/bin/bash
# Deployment script for Travel Tracker API to travel-tracker-9674d

set -e  # Exit on error

PROJECT_ID="travel-tracker-9674d"
SERVICE_NAME="travel-tracker-api"
REGION="us-central1"  # Change if needed
REPO_URL="https://github.com/gaurseth/api-travel-tracker.git"

echo "🚀 Travel Tracker API - Cloud Run Deployment"
echo "=============================================="
echo ""
echo "📦 Project: $PROJECT_ID"
echo "🌎 Region: $REGION"
echo "📝 Service: $SERVICE_NAME"
echo ""

# Step 1: Set project
echo "Step 1: Setting Google Cloud project..."
gcloud config set project $PROJECT_ID
echo "✅ Project set to: $PROJECT_ID"
echo ""

# Step 2: Enable required APIs
echo "Step 2: Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  firestore.googleapis.com \
  vision.googleapis.com \
  artifactregistry.googleapis.com \
  --project=$PROJECT_ID

echo "✅ APIs enabled"
echo ""

# Step 3: Deploy to Cloud Run
echo "Step 3: Deploying to Cloud Run..."
echo "This will:"
echo "  - Build your Docker image"
echo "  - Deploy to Cloud Run"
echo "  - Set environment variables"
echo ""

gcloud run deploy $SERVICE_NAME \
  --source . \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars DEV_MODE=false \
  --memory 512Mi \
  --timeout 300 \
  --project=$PROJECT_ID

echo ""
echo "✅ Deployment complete!"
echo ""

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --platform managed \
  --region $REGION \
  --format 'value(status.url)' \
  --project=$PROJECT_ID)

echo "=============================================="
echo "🎉 Deployment Successful!"
echo "=============================================="
echo ""
echo "Service URL: $SERVICE_URL"
echo ""
echo "Test endpoints:"
echo "  curl $SERVICE_URL/health"
echo "  curl $SERVICE_URL/"
echo ""
echo "Swagger UI:"
echo "  $SERVICE_URL/docs"
echo ""
echo "⚠️  Note: DEV_MODE=false (production mode)"
echo "   All endpoints require Firebase authentication"
echo ""
