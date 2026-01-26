#!/bin/bash

# --- CONFIGURATION ---
PROJECT_ID="your-google-cloud-project-id"
BUCKET_NAME="your-podcast-bucket-name"
REGION="us-central1"
SERVICE_NAME="lazy-podinator"
ANTHROPIC_API_KEY="your-anthropic-api-key"
# ---------------------

echo "================================================"
echo "Step 1: Uploading Configuration"
echo "================================================"

# Upload shows_config.json to GCS for dynamic updates
echo "Uploading shows_config.json to gs://$BUCKET_NAME/config/..."
gcloud storage cp shows_config.json gs://$BUCKET_NAME/config/shows_config.json
echo "✓ Configuration uploaded"
echo ""

echo "================================================"
echo "Step 2: Uploading Podcast Artwork"
echo "================================================"

# Upload artwork files to GCS
if [ -d "artwork" ]; then
    ARTWORK_COUNT=$(find artwork -name "*.jpg" -o -name "*.png" | wc -l | tr -d ' ')

    if [ "$ARTWORK_COUNT" -gt 0 ]; then
        echo "Found $ARTWORK_COUNT artwork file(s), uploading to gs://$BUCKET_NAME/artwork/..."
        gcloud storage cp artwork/*.jpg gs://$BUCKET_NAME/artwork/ 2>/dev/null || true
        gcloud storage cp artwork/*.png gs://$BUCKET_NAME/artwork/ 2>/dev/null || true
        echo "✓ Artwork uploaded successfully"
    else
        echo "⚠ No artwork files found in artwork/ directory"
        echo "  Add artwork files (stablecoin.jpg, ai.jpg, etc.) for podcast covers"
    fi
else
    echo "⚠ No artwork directory found"
fi

echo ""
echo "================================================"
echo "Step 3: Building and Deploying to Cloud Run"
echo "================================================"

# Build and deploy using Cloud Build (builds the Docker image and deploys)
gcloud run deploy $SERVICE_NAME \
    --source=. \
    --region=$REGION \
    --platform=managed \
    --allow-unauthenticated \
    --memory=1Gi \
    --cpu=1 \
    --timeout=300s \
    --set-env-vars BUCKET_NAME=$BUCKET_NAME,ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
    --project=$PROJECT_ID

echo ""
echo "================================================"
echo "Deployment Complete!"
echo "================================================"
echo ""
echo "To set up the daily trigger, run:"
echo "gcloud scheduler jobs create http daily-pod-trigger \\"
echo "    --schedule=\"0 13 * * *\" \\"  # 8:00 AM EST (13:00 UTC)
echo "    --uri=\"\$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')\" \\"
echo "    --http-method=GET \\"
echo "    --location=$REGION \\"
echo "    --project=$PROJECT_ID"
