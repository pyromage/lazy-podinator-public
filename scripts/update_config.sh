#!/bin/bash
# Update shows_config.json in GCS without redeploying

set -e

# --- LOAD ENVIRONMENT VARIABLES ---
if [ -f .env ]; then
    echo "Loading configuration from .env file..."
    source .env
else
    echo "❌ Error: .env file not found"
    echo "Please create a .env file based on .env.example"
    exit 1
fi

# Validate required variables
if [ -z "$BUCKET_NAME" ]; then
    echo "❌ Error: BUCKET_NAME not set in .env"
    exit 1
fi

echo "================================================"
echo "Updating Podcast Configuration"
echo "================================================"
echo ""

if [ ! -f "shows_config.json" ]; then
    echo "❌ Error: shows_config.json not found"
    exit 1
fi

echo "📤 Uploading shows_config.json to gs://$BUCKET_NAME/config/..."
gcloud storage cp shows_config.json gs://$BUCKET_NAME/config/shows_config.json

if [ -f "pronunciation_guide.json" ]; then
    echo "📤 Uploading pronunciation_guide.json to gs://$BUCKET_NAME/config/..."
    gcloud storage cp pronunciation_guide.json gs://$BUCKET_NAME/config/pronunciation_guide.json
fi

echo ""
echo "✅ Configuration updated!"
echo ""
echo "Changes will take effect on the next podcast run (8:00 AM EST)."
echo "Or trigger manually:"
echo "  gcloud scheduler jobs run daily-pod-trigger --location=us-central1"
