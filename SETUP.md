# Setup Guide

## Prerequisites

- Python 3.11+
- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) (`gcloud`) installed and authenticated
- [Anthropic API key](https://console.anthropic.com/)
- GCP project with billing enabled

## 1. Clone and Install

```bash
git clone https://github.com/yourusername/lazy-podinator.git
cd lazy-podinator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure

```bash
cp shows_config.example.json shows_config.json
cp .env.example .env
```

Edit `.env` with your values:

```bash
export ANTHROPIC_API_KEY="your-key"
export CLAUDE_MODEL="claude-sonnet-4-6"
export PROJECT_ID="your-gcp-project-id"
export BUCKET_NAME="your-podcast-bucket-name"
export REGION="northamerica-northeast1"
export SERVICE_NAME="lazy-podinator"
export NOTIFY_EMAIL="your-gmail@gmail.com"
```

Edit `shows_config.json` to define your podcasts. Each show needs:

| Field | Description |
| --- | --- |
| `title` | Podcast name |
| `description` | Show description for podcast apps |
| `author` | Your name or org |
| `email` | Contact email (required by podcast directories) |
| `category` | News, Technology, Business, Science, etc. |
| `artwork` | Cover image URL (1400x1400 to 3000x3000 px) |
| `voice` | Piper TTS voice model |
| `duration` | Estimated duration in seconds ("600" = 10 min) |
| `feeds` | Array of RSS feed URLs |
| `keywords` | Array of topic keywords for AI selection |

See `shows_config.example.json` for a template.

### Available Piper Voices

- `en_US-ryan-high` — deep male voice
- `en_US-amy-medium` — energetic female voice
- `en_US-lessac-medium` — neutral, clear voice
- `en_GB-alan-medium` — British male voice

Full list: <https://rhasspy.github.io/piper-samples/>

## 3. Test Locally

```bash
source .env

# Generate scripts only (no audio)
python test/test_local.py

# Test audio with Docker (recommended, matches production)
chmod +x test/test_audio_docker.sh
./test/test_audio_docker.sh

# Play the output
afplay output/stablecoin_podcast.mp3
```

## 4. GCP Setup

### Enable APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com \
  gmail.googleapis.com
```

### Create Storage Bucket

```bash
gcloud storage buckets create gs://YOUR_BUCKET_NAME --location=$REGION

# Make publicly readable (required for podcast apps)
gcloud storage buckets add-iam-policy-binding gs://YOUR_BUCKET_NAME \
  --member=allUsers \
  --role=roles/storage.objectViewer
```

### Create Podcast Artwork

Add cover images (1400x1400 to 3000x3000 px) to the `artwork/` directory. The deploy script uploads them automatically.

## 5. Gmail Notifications (Optional)

Sends an email alert when the pipeline fails.

### One-time OAuth Setup

1. In GCP Console: **APIs & Services > Credentials > Create Credentials > OAuth client ID** (type: Desktop app)
2. Download the JSON and save as `gmail_credentials.json` in the project root
3. Set up the OAuth consent screen (External, Testing mode, add your email as a test user)
4. Run the setup script:

```bash
source .env
python scripts/setup_gmail.py
```

This opens a browser for authorization, then uploads the token to GCS.

## 6. Deploy

```bash
source .env
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

This builds the Docker container, uploads config and artwork, and deploys to Cloud Run.

## 7. Schedule Daily Runs

```bash
gcloud scheduler jobs create http daily-pod-trigger \
  --schedule="0 13 * * *" \
  --uri="$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')" \
  --http-method=GET \
  --location=$REGION
```

`0 13 * * *` = 8:00 AM EST (13:00 UTC). Adjust for your timezone.

### Manual Trigger

```bash
gcloud scheduler jobs run daily-pod-trigger --location=$REGION
```

## 8. Updating Config (No Redeploy)

Show config is stored in GCS and can be updated without redeploying:

```bash
./scripts/update_config.sh
```

Only redeploy when you change Python code, dependencies, or the Dockerfile.

## 9. Listen

After the first episode generates, RSS feeds are available at:

```text
https://storage.googleapis.com/YOUR_BUCKET/SHOW_KEY/feed.xml
```

Submit to [Spotify for Podcasters](https://podcasters.spotify.com), [Apple Podcasts Connect](https://podcastsconnect.apple.com), or add the RSS URL to any podcast app.

## Troubleshooting

```bash
# Check Cloud Run logs
gcloud run services logs read $SERVICE_NAME --region=$REGION --limit=100

# Test a single RSS feed
python -c "import feedparser; print(len(feedparser.parse('URL').entries))"

# Test Piper TTS directly
echo "test" | ./piper/piper --model ./piper/models/en_US-ryan-high.onnx --output_file test.wav
```
