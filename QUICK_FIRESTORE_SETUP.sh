#!/bin/bash
# Quick Firestore Setup Script for Travel Tracker API

echo "🚀 Travel Tracker API - Firestore Setup"
echo "========================================"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ Google Cloud SDK not found. Please install it first:"
    echo "   https://cloud.google.com/sdk/docs/install"
    exit 1
fi

echo "✅ Google Cloud SDK found"
echo ""

# Get current project
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)
if [ -z "$CURRENT_PROJECT" ]; then
    echo "❌ No Google Cloud project configured."
    echo "   Please run: gcloud init"
    exit 1
fi

echo "📦 Current project: $CURRENT_PROJECT"
echo ""

# Enable Firestore API
echo "🔧 Enabling Firestore API..."
gcloud services enable firestore.googleapis.com --project=$CURRENT_PROJECT
echo "✅ Firestore API enabled"
echo ""

# Check if service account exists
SERVICE_ACCOUNT_NAME="travel-tracker-dev"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${CURRENT_PROJECT}.iam.gserviceaccount.com"

echo "🔍 Checking for existing service account..."
if gcloud iam service-accounts describe $SERVICE_ACCOUNT_EMAIL &>/dev/null; then
    echo "✅ Service account already exists: $SERVICE_ACCOUNT_EMAIL"
else
    echo "📝 Creating service account..."
    gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
        --display-name="Travel Tracker Dev Service Account" \
        --project=$CURRENT_PROJECT
    echo "✅ Service account created"
fi
echo ""

# Grant Firestore permissions
echo "🔐 Granting Firestore permissions..."
gcloud projects add-iam-policy-binding $CURRENT_PROJECT \
    --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
    --role="roles/datastore.user" \
    --quiet

echo "✅ Firestore permissions granted"
echo ""

# Download credentials
CREDENTIALS_FILE="$HOME/.config/gcloud/travel-tracker-credentials.json"
echo "📥 Downloading service account key to: $CREDENTIALS_FILE"

if [ -f "$CREDENTIALS_FILE" ]; then
    echo "⚠️  Credentials file already exists. Skipping download."
else
    mkdir -p "$HOME/.config/gcloud"
    gcloud iam service-accounts keys create $CREDENTIALS_FILE \
        --iam-account=$SERVICE_ACCOUNT_EMAIL \
        --project=$CURRENT_PROJECT
    echo "✅ Credentials downloaded"
fi
echo ""

# Set environment variable
echo "🔧 Setting up environment variable..."
export GOOGLE_APPLICATION_CREDENTIALS="$CREDENTIALS_FILE"

# Add to shell profile
SHELL_PROFILE=""
if [ -f "$HOME/.zshrc" ]; then
    SHELL_PROFILE="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_PROFILE="$HOME/.bashrc"
elif [ -f "$HOME/.bash_profile" ]; then
    SHELL_PROFILE="$HOME/.bash_profile"
fi

if [ -n "$SHELL_PROFILE" ]; then
    if ! grep -q "GOOGLE_APPLICATION_CREDENTIALS.*travel-tracker-credentials" "$SHELL_PROFILE"; then
        echo "" >> "$SHELL_PROFILE"
        echo "# Travel Tracker API - Google Cloud Credentials" >> "$SHELL_PROFILE"
        echo "export GOOGLE_APPLICATION_CREDENTIALS=\"$CREDENTIALS_FILE\"" >> "$SHELL_PROFILE"
        echo "✅ Added to $SHELL_PROFILE"
    else
        echo "✅ Already in $SHELL_PROFILE"
    fi
fi
echo ""

# Create Firestore database (if needed)
echo "🗄️  Checking Firestore database..."
if gcloud firestore databases list --project=$CURRENT_PROJECT 2>/dev/null | grep -q "ACTIVE"; then
    echo "✅ Firestore database already exists"
else
    echo "📝 Creating Firestore database..."
    echo ""
    echo "⚠️  IMPORTANT: You need to create the Firestore database manually:"
    echo "   1. Go to: https://console.cloud.google.com/firestore?project=$CURRENT_PROJECT"
    echo "   2. Click 'Create Database'"
    echo "   3. Choose 'Native Mode'"
    echo "   4. Select a region (recommend: us-central1)"
    echo "   5. Start in 'Production mode'"
    echo ""
fi

echo ""
echo "✅ Setup Complete!"
echo "===================="
echo ""
echo "📋 Next steps:"
echo "   1. Restart your terminal OR run:"
echo "      export GOOGLE_APPLICATION_CREDENTIALS=\"$CREDENTIALS_FILE\""
echo ""
echo "   2. Verify credentials:"
echo "      echo \$GOOGLE_APPLICATION_CREDENTIALS"
echo ""
echo "   3. If Firestore database doesn't exist, create it:"
echo "      https://console.cloud.google.com/firestore?project=$CURRENT_PROJECT"
echo ""
echo "   4. Start your API:"
echo "      cd /Users/gaurav/Documents/travel-tracker-api"
echo "      uvicorn main:app --reload"
echo ""
echo "🎉 Happy coding!"
