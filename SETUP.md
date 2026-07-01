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
| `voice` | TTS voice (Piper name; auto-mapped to a Kokoro voice when `TTS_ENGINE=kokoro`) |
| `duration` | Estimated duration in seconds ("600" = 10 min) |
| `feeds` | Array of RSS feed URLs |
| `keywords` | Array of topic keywords for AI selection |

See `shows_config.example.json` for a template.

### Voices

The `voice` field accepts Piper voice-model names. When `TTS_ENGINE=kokoro`
(the default), these are auto-mapped to Kokoro voices:

| `voice` value | Description | Kokoro voice |
| --- | --- | --- |
| `en_US-ryan-high` | deep, authoritative male | `am_michael` |
| `en_US-amy-medium` | energetic female | `af_heart` |

To use a Kokoro voice directly, put its native name (e.g. `am_adam`,
`af_bella`) in the `voice` field — unmapped values are passed through as-is.

- Piper voice list: <https://rhasspy.github.io/piper-samples/>
- Kokoro voice list: <https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md>

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

> **Note on Cloud Run + Kokoro:** Cloud Run caps a request at 60 minutes. With
> Kokoro TTS on 2 vCPU, three ~10-minute episodes take longer than that, so the
> scheduled HTTP run will time out. Use the GitHub Actions path below (free,
> 4-vCPU runners, no 60-minute cap), or set `TTS_ENGINE=piper` for Cloud Run.

## Free Daily Runs via GitHub Actions (recommended)

Standard GitHub-hosted runners are **free and unlimited on public repositories**
(4 vCPU, 6-hour job limit), which comfortably fits a full Kokoro run. The
workflow ([.github/workflows/daily.yml](.github/workflows/daily.yml)) reads
config from GCS and publishes episodes/feeds to GCS — the same data flow as
Cloud Run — so no container or Cloud Run service is needed.

Authentication uses **Workload Identity Federation** (keyless GitHub OIDC → GCP)
— no service-account JSON key, which many orgs disable by policy.

1. **Create a service account** with write access to your bucket:

   ```bash
   REPO="<owner>/<repo>"   # your public repo
   SA="podinator-ci@$PROJECT_ID.iam.gserviceaccount.com"
   NUM=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

   gcloud iam service-accounts create podinator-ci \
     --display-name="Podinator GitHub Actions" --project=$PROJECT_ID
   gcloud storage buckets add-iam-policy-binding gs://$BUCKET_NAME \
     --member="serviceAccount:$SA" --role="roles/storage.objectAdmin"
   ```

2. **Set up Workload Identity Federation**, scoped to your repo:

   ```bash
   gcloud iam workload-identity-pools create github-pool \
     --project=$PROJECT_ID --location=global --display-name="GitHub Actions"
   gcloud iam workload-identity-pools providers create-oidc github-provider \
     --project=$PROJECT_ID --location=global --workload-identity-pool=github-pool \
     --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
     --attribute-condition="assertion.repository=='$REPO'" \
     --issuer-uri="https://token.actions.githubusercontent.com"
   gcloud iam service-accounts add-iam-policy-binding $SA --project=$PROJECT_ID \
     --role="roles/iam.workloadIdentityUser" \
     --member="principalSet://iam.googleapis.com/projects/$NUM/locations/global/workloadIdentityPools/github-pool/attribute.repository/$REPO"
   ```

3. **Add repository secrets** (public repo → Settings → Secrets and variables →
   Actions). None are private keys, but keeping them out of the public YAML avoids
   hardcoding project-specific values:

   | Secret | Value |
   | --- | --- |
   | `GCP_WIF_PROVIDER` | `projects/$NUM/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |
   | `GCP_SA_EMAIL` | `podinator-ci@$PROJECT_ID.iam.gserviceaccount.com` |
   | `ANTHROPIC_API_KEY` | your Anthropic API key |
   | `BUCKET_NAME` | your GCS bucket name |
   | `NOTIFY_EMAIL` | failure-notification address (optional) |

4. **Edit the repo guard** in `daily.yml` (`github.repository == '...'`) to your
   public repo's `owner/name`, and adjust the `cron` time (UTC) if desired.

The workflow runs daily and can be triggered manually from the **Actions** tab.

> Caveats: scheduled workflows are auto-disabled after 60 days of repo
> inactivity (push or re-enable to resume), and run in UTC. Failure emails
> require the Gmail setup below; otherwise a failed run still shows in the
> Actions tab.

## 7. Schedule Daily Runs (Cloud Run)

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

# Test Kokoro TTS directly (default engine)
python -c "import soundfile as sf; from kokoro_onnx import Kokoro; k = Kokoro('/app/kokoro/kokoro-v1.0.int8.onnx', '/app/kokoro/voices-v1.0.bin'); s, r = k.create('test', voice='am_michael', lang='en-us'); sf.write('test.wav', s, r)"

# Test Piper TTS directly (fallback engine)
echo "test" | ./piper/piper --model ./piper/models/en_US-ryan-high.onnx --output_file test.wav
```
