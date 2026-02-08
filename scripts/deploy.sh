#!/bin/bash

# --- LOAD ENVIRONMENT VARIABLES ---
if [ -f .env ]; then
    echo "Loading configuration from .env file..."
    source .env
else
    echo "❌ Error: .env file not found"
    echo "Please create a .env file based on .env.example"
    exit 1
fi

# --- CONFIGURATION ---
REGION="northamerica-northeast1"  # Montreal
SERVICE_NAME="lazy-podinator"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${SERVICE_NAME}:latest"
# ---------------------

# Validate required variables
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "❌ Error: ANTHROPIC_API_KEY not set in .env"
    exit 1
fi

if [ -z "$PROJECT_ID" ]; then
    echo "❌ Error: PROJECT_ID not set in .env"
    exit 1
fi

if [ -z "$BUCKET_NAME" ]; then
    echo "❌ Error: BUCKET_NAME not set in .env"
    exit 1
fi

echo "================================================"
echo "Step 1: Uploading Configuration"
echo "================================================"

# Upload shows_config.json to GCS for dynamic updates
echo "Uploading shows_config.json to gs://$BUCKET_NAME/config/..."
gcloud storage cp shows_config.json gs://$BUCKET_NAME/config/shows_config.json

# Upload pronunciation_guide.json to GCS
if [ -f "pronunciation_guide.json" ]; then
    echo "Uploading pronunciation_guide.json to gs://$BUCKET_NAME/config/..."
    gcloud storage cp pronunciation_guide.json gs://$BUCKET_NAME/config/pronunciation_guide.json
fi
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
echo "Step 3: Building Docker Image with Cloud Build"
echo "================================================"

# Build image using Cloud Build (avoids restricted run-sources-* bucket)
gcloud builds submit \
    --project=$PROJECT_ID \
    --region=$REGION \
    --tag=$IMAGE \
    .

echo ""
echo "================================================"
echo "Step 4: Deploying to Cloud Run"
echo "================================================"

# Deploy the pre-built image to Cloud Run
gcloud run deploy $SERVICE_NAME \
    --image=$IMAGE \
    --region=$REGION \
    --platform=managed \
    --allow-unauthenticated \
    --memory=1Gi \
    --cpu=1 \
    --timeout=1800s \
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
