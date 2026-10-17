# Setup Guide

The recommended setup runs the pipeline daily on **GitHub Actions** (free on
public repos) and publishes to **Google Cloud Storage**. Cloud Run is supported
as an optional alternative.

## Prerequisites

- Python 3.11+
- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) (`gcloud`) installed and authenticated
- [GitHub CLI](https://cli.github.com/) (`gh`) — optional, for triggering and inspecting runs
- [Anthropic API key](https://console.anthropic.com/)
- GCP project with billing enabled
- A **public** GitHub repo (your fork) — Actions minutes are free and unlimited on public repos

## 1. Fork, Clone and Install

Fork [pyromage/lazy-podinator-public](https://github.com/pyromage/lazy-podinator-public), then:

```bash
git clone https://github.com/<your-username>/lazy-podinator-public.git
cd lazy-podinator-public
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure

```bash
cp shows_config.example.json shows_config.json
cp .env.example .env
```

Both copies are gitignored — your personal config never gets committed.

Edit `.env` with your values:

```bash
export ANTHROPIC_API_KEY="your-key"
export CLAUDE_MODEL="claude-sonnet-5-5"
export CLAUDE_FALLBACK_MODEL="claude-sonnet-5"   # used if the primary model refuses
export CLAUDE_EFFORT="medium"                    # article selection
export CLAUDE_SCRIPT_EFFORT="high"               # script writing (affects length)
export TTS_ENGINE="kokoro"                       # or "piper"
export PROJECT_ID="your-gcp-project-id"
export BUCKET_NAME="your-podcast-bucket-name"
export REGION="your-gcp-region"
export NOTIFY_EMAIL="your-gmail@gmail.com"       # optional, Gmail alerts only
```

Edit `shows_config.json` to define your podcasts. Each top-level key is a show
(the key is used in file and feed paths). Each show has:

| Field | Description |
| --- | --- |
| `title` | Podcast name |
| `description` | Show description for podcast apps |
| `author` | Your name or org |
| `email` | Contact email (required by podcast directories; appears in the public feed) |
| `category` | News, Technology, Business, Science, etc. |
| `artwork` | Cover image URL (1400x1400 to 3000x3000 px) |
| `voice` | TTS voice (Piper name; auto-mapped to a Kokoro voice when `TTS_ENGINE=kokoro`) |
| `duration` | Target episode length in seconds ("600" = 10 min); drives script length at ~185 words/min |
| `feeds` | Array of RSS feed URLs |
| `keywords` | Array of topic keywords for AI selection |
| `interests` | Array of priorities that guide which stories Claude picks |
| `linkedin_top_content` | Optional array of LinkedIn top-content page URLs |
| `gmail_labels` | Optional array of Gmail labels to pull newsletters from (requires Gmail setup, step 6) |

See `shows_config.example.json` for a template.

### Choosing Feeds

Story quality depends more on sources than on the model. Prefer feeds whose
article pages return real HTML to a script:

- **Avoid** sites behind Cloudflare bot challenges or that return 403 to scripts — the pipeline discards those pages and falls back to the short RSS summary
- **Avoid** Google News search feeds — their links are redirect stubs with ~85-character summaries
- **Google Alerts** RSS feeds work — the pipeline unwraps their redirect links
- After a test run, check the per-show "N full articles, N summary-only" line in the output; a show with mostly summary-only articles needs better feeds

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

# Generate scripts only (no audio) — quickest check
python test/test_local.py

# Generate audio from those scripts via the real pipeline (Kokoro default)
./scripts/setup_kokoro.sh
export TTS_ENGINE=kokoro
export KOKORO_MODEL_PATH=./kokoro/kokoro-v1.0.int8.onnx
export KOKORO_VOICES_PATH=./kokoro/voices-v1.0.bin
python test/test_audio.py          # writes output/<show>_podcast.mp3
afplay output/<show>_podcast.mp3   # macOS; use any audio player elsewhere
```

Scripts are written to `output/` — read them to check quality and length
before going live. For production parity, `./test/test_audio_docker.sh` runs
the same audio step inside the Docker image, with the Kokoro model baked in.

## 4. GCP Setup

### Enable APIs

```bash
gcloud services enable \
  storage.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com
```

Add `gmail.googleapis.com` for Gmail alerts or newsletters (step 6), and the
Cloud Run APIs only if you use step 7.

### Create Storage Bucket

```bash
gcloud storage buckets create gs://$BUCKET_NAME --location=$REGION

# Make publicly readable (required for podcast apps)
gcloud storage buckets add-iam-policy-binding gs://$BUCKET_NAME \
  --member=allUsers \
  --role=roles/storage.objectViewer
```

### Upload Config and Artwork

The pipeline reads its config from the bucket at runtime, so config changes
never need a code push or redeploy:

```bash
./scripts/update_config.sh                      # uploads shows_config.json (+ pronunciation_guide.json)
gcloud storage cp artwork/*.png gs://$BUCKET_NAME/artwork/
```

Cover images should be 1400x1400 to 3000x3000 px. Point each show's `artwork`
field at `https://storage.googleapis.com/<bucket>/artwork/<file>`.

## 5. Daily Runs via GitHub Actions (recommended)

Standard GitHub-hosted runners are **free and unlimited on public repositories**
(4 vCPU, 6-hour job limit), which comfortably fits a full Kokoro run (~40–50
minutes for three ~11-minute shows). The workflow
([.github/workflows/daily.yml](.github/workflows/daily.yml)) reads config from
GCS and publishes episodes and feeds to GCS — no container or Cloud Run service
is needed.

Authentication uses **Workload Identity Federation** (keyless GitHub OIDC → GCP)
— no service-account JSON key, which many orgs disable by policy.

1. **Create a service account** with write access to your bucket:

   ```bash
   REPO="<owner>/<repo>"   # your public fork
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

3. **Add repository secrets** (your repo → Settings → Secrets and variables →
   Actions). None are private keys, but keeping them out of the public YAML avoids
   hardcoding project-specific values:

   | Secret | Value |
   | --- | --- |
   | `GCP_WIF_PROVIDER` | `projects/$NUM/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |
   | `GCP_SA_EMAIL` | `podinator-ci@$PROJECT_ID.iam.gserviceaccount.com` |
   | `ANTHROPIC_API_KEY` | your Anthropic API key |
   | `BUCKET_NAME` | your GCS bucket name |
   | `NOTIFY_EMAIL` | failure-notification address (optional, Gmail alerts only) |

4. **Edit the repo guard** in `daily.yml` (`github.repository == '...'`) to your
   repo's `owner/name` — otherwise the job is skipped. Adjust the `cron` time
   (UTC) if desired.

5. **Enable Actions** on your fork (forks start with workflows disabled: open
   the **Actions** tab and enable them), then trigger a first run:

   ```bash
   gh workflow run daily.yml --repo <owner>/<repo>
   ```

### What the Workflow Handles for You

- **Auto-retry** — if a run fails, `retry.yml` reruns it once on a fresh runner. Generation is idempotent, so the rerun only regenerates shows still missing for the day.
- **Partial success** — if one show fails, the others still publish and feeds are refreshed.
- **Failure alerts** — if the retry also fails, the workflow opens a GitHub issue assigned to the repo owner, so GitHub emails you. No Gmail setup needed.
- **Keepalive** — GitHub disables scheduled workflows after 60 days without repo activity. The workflow re-enables itself on every run to prevent this.

> If runs fail in about a minute, check your Anthropic credit balance first —
> billing errors fail fast by design. Consider enabling auto-reload in the
> Anthropic console.

## 6. Gmail Integration (Optional)

Gmail is used for two optional features: pulling newsletters by label
(`gmail_labels` in a show config) and sending failure emails. Neither is needed
for the core pipeline — GitHub issue alerts (step 5) cover failures.

### One-time OAuth Setup

1. In GCP Console: **APIs & Services > Credentials > Create Credentials > OAuth client ID** (type: Desktop app)
2. Download the JSON and save as `gmail_credentials.json` in the project root (gitignored)
3. Set up the OAuth consent screen (External, add your email as a test user)
4. Run the setup script:

```bash
source .env
python scripts/setup_gmail.py
```

This opens a browser for authorization, then uploads the token to GCS
(`config/gmail_token.json`).

> **Token expiry:** while the OAuth app is in **Testing** status, Google
> expires refresh tokens after 7 days, and Gmail calls then fail with
> `invalid_grant`. Publish the app to **In production** on the consent screen
> for long-lived tokens, or rerun `setup_gmail.py` when it expires. The pipeline
> skips Gmail silently if it is not configured.

## 7. Cloud Run (Optional Alternative)

Use this only if you prefer Cloud Run to GitHub Actions. Enable the extra APIs:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com artifactregistry.googleapis.com
```

Set `SERVICE_NAME` in `.env`, then deploy:

```bash
source .env
./scripts/deploy.sh
```

This builds the Docker container, uploads config and artwork, and deploys to Cloud Run.

> **Cloud Run + Kokoro:** Cloud Run caps a request at 60 minutes. With Kokoro
> TTS on 2 vCPU, several ~10-minute episodes can take longer than that, so the
> scheduled HTTP run may time out. Set `TTS_ENGINE=piper` for Cloud Run, or use
> GitHub Actions.

Schedule a daily trigger:

```bash
gcloud scheduler jobs create http daily-pod-trigger \
  --schedule="0 11 * * *" \
  --uri="$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')" \
  --http-method=GET \
  --location=$REGION

# Manual trigger
gcloud scheduler jobs run daily-pod-trigger --location=$REGION
```

`0 11 * * *` = 11:00 UTC. Adjust for your timezone. Redeploy only when you
change Python code, dependencies, or the Dockerfile.

## 8. Updating Config

Shows, feeds, keywords and voices live in GCS. To change them, edit your local
`shows_config.json` and run:

```bash
./scripts/update_config.sh
```

Changes take effect on the next run. Keep your local copy and the GCS copy in
sync — the GCS copy is what production uses.

## 9. Listen

After the first episode generates, RSS feeds are available at:

```text
https://storage.googleapis.com/YOUR_BUCKET/SHOW_KEY/feed.xml
```

Submit to [Spotify for Podcasters](https://podcasters.spotify.com), [Apple Podcasts Connect](https://podcastsconnect.apple.com), or add the RSS URL to any podcast app.

## Troubleshooting

```bash
# Recent GitHub Actions runs and logs
gh run list --workflow=daily.yml --repo <owner>/<repo>
gh run view <run-id> --log --repo <owner>/<repo>

# Cloud Run logs (if used)
gcloud run services logs read $SERVICE_NAME --region=$REGION --limit=100

# Test a single RSS feed
python -c "import feedparser; print(len(feedparser.parse('URL').entries))"

# Test Kokoro TTS directly (default engine)
python -c "import soundfile as sf; from kokoro_onnx import Kokoro; k = Kokoro('./kokoro/kokoro-v1.0.int8.onnx', './kokoro/voices-v1.0.bin'); s, r = k.create('test', voice='am_michael', lang='en-us'); sf.write('test.wav', s, r)"

# Test Piper TTS directly (fallback engine)
echo "test" | ./piper/piper --model ./piper/models/en_US-ryan-high.onnx --output_file test.wav
```

| Symptom | Likely cause |
| --- | --- |
| Run fails in ~1 minute | Anthropic credits depleted — top up and enable auto-reload |
| Workflow job shows "skipped" | Repo guard in `daily.yml` doesn't match your repo name |
| Episodes much shorter than `duration` | Feeds returning block pages or summary-only text — see Choosing Feeds |
| Gmail `invalid_grant` | OAuth app in Testing status — see Token expiry in step 6 |
| Schedule stopped running | Workflow disabled — re-enable in the Actions tab (keepalive prevents recurrence) |
