#!/bin/bash
# Update shows_config.json in GCS without redeploying

# --- CONFIGURATION ---
# Load from deploy.sh or set here
BUCKET_NAME="${BUCKET_NAME:-your-podcast-bucket-name}"
# ---------------------

set -e

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

echo ""
echo "✅ Configuration updated!"
echo ""
echo "Changes will take effect on the next podcast run (8:00 AM EST)."
echo "Or trigger manually:"
echo "  gcloud scheduler jobs run daily-pod-trigger --location=us-central1"
