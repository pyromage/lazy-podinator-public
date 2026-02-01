# Lazy Podinator

Serverless, "set-and-forget" automation engine that turns raw RSS feeds and email newsletters into high-quality, AI-hosted daily podcasts. Built for developers who want a daily audio briefing on specific niche topics (e.g., Stablecoins, AI, BioTech) without the manual effort of reading newsletters.

## What It Does

Every morning at 8:00 AM EST (or your preferred time), Lazy Podinator:

1. **Ingests:** Scrapes headlines from the last 3 days via RSS feeds and email newsletters in your inbox (TLDR, Morning Brew, etc.).
2. **Analyzes:** Uses Anthropic Claude to act as an "Executive Producer"—selecting up to 20 of the most relevant topics for each show.
3. **Scripts:** Writes a 30-second professional summary for each topic, creating a ~10 minute podcast per show.
4. **Broadcasts:** Generates an HD audio file using Piper TTS (free, local text-to-speech).
5. **Delivers:** Uploads the final MP3 and RSS feed to Google Cloud Storage.
6. **Distributes:** Auto-generates podcast RSS feeds compatible with Spotify, Apple Podcasts, and other apps.

## Architecture

The system runs entirely on **Google Cloud Platform (Serverless)**.

* **Compute:** Google Cloud Run (Docker container)
* **Trigger:** Google Cloud Scheduler (Cron)
* **Storage:** Google Cloud Storage (Buckets)
* **Intelligence:** Anthropic Claude API
* **TTS:** Piper TTS (free, open-source, runs locally in container)

## Project Structure

```text
lazy-podinator/
├── main.py                      # Main application (Flask server + podcast generation)
├── Dockerfile                   # Docker build configuration for Cloud Run
├── requirements.txt             # Python dependencies
├── shows_config.json            # Podcast show configuration (feeds, keywords, voices)
├── .env                         # Environment variables (not in git)
├── .env.example                 # Example environment variables
├── .gitignore                   # Git ignore rules
├── README.md                    # This file
├── LICENSE                      # MIT License
├── scripts/                     # Deployment and utility scripts
│   ├── deploy.sh               # Main deployment script for Cloud Run
│   ├── update_config.sh        # Update shows_config.json without redeploying
│   └── setup_piper_macos.sh    # Local Piper TTS setup for macOS
├── test/                        # Testing scripts
│   ├── test_local.py           # Test script generation (no audio)
│   ├── test_audio.py           # Test audio generation with local Piper
│   ├── test_audio_docker.sh    # Test audio with Docker (recommended)
│   ├── test_audio_macos.sh     # Test audio with macOS 'say' command
│   └── test_cleanup.py         # Test 30-day cleanup functionality
├── docs/                        # Additional documentation
│   └── requirements.md         # Original requirements specification
├── artwork/                     # Podcast cover art (1400x1400 to 3000x3000 px)
│   ├── README.md               # Artwork creation guide
│   ├── stablecoin.png          # Cover for The Stablecoin Ledger
│   └── ai.png                  # Cover for AI Technology Morning Brief
└── output/                      # Generated files (local testing only)
    ├── scripts.json            # Generated podcast scripts
    ├── stablecoin_script.txt   # Individual show scripts
    ├── ai_script.txt
    ├── stablecoin_podcast.mp3  # Generated audio files
    └── ai_podcast.mp3
```

## Prerequisites

* **Google Cloud Platform Account** (Free Tier is sufficient)
  * Enable APIs: `Cloud Run`, `Cloud Build`, `Cloud Storage`, `Cloud Scheduler`, `Artifact Registry`
* **Anthropic API Key** (Get one at [console.anthropic.com](https://console.anthropic.com/))
* **Google Cloud CLI (`gcloud`)** installed and authenticated

## Configuration

### Shows Configuration

Edit `shows_config.json` to customize your podcasts. Each show has its own curated list of RSS feeds, Gmail labels, and keywords:

```json
{
  "stablecoin": {
    "title": "The Stablecoin Ledger",
    "description": "Your daily 10-minute briefing on stablecoins, payments, and digital finance.",
    "author": "Your Name",
    "email": "you@example.com",
    "category": "News",
    "artwork": "https://storage.googleapis.com/YOUR_BUCKET/artwork/stablecoin.png",
    "voice": "en_US-ryan-high",
    "duration": "600",
    "feeds": [
      "https://www.coindesk.com/arc/outboundfeeds/rss/",
      "https://www.finextra.com/rss/channel.aspx?channel=payments",
      "https://www.paymentsdive.com/feeds/news/"
    ],
    "keywords": ["stablecoin", "USDC", "USDT", "payments", "defi"]
  },
  "ai": {
    "title": "AI Technology Morning Brief",
    "description": "Your daily 10-minute AI news digest.",
    "author": "Your Name",
    "email": "you@example.com",
    "category": "Technology",
    "artwork": "https://storage.googleapis.com/YOUR_BUCKET/artwork/ai.png",
    "voice": "en_US-amy-medium",
    "duration": "600",
    "feeds": [
      "https://techcrunch.com/category/artificial-intelligence/feed/",
      "https://www.finextra.com/rss/channel.aspx?channel=ai"
    ],
    "keywords": ["LLM", "transformer", "generative ai", "neural", "openai"]
  }
}
```

**Configuration Fields:**

* `title` - Podcast name (required)
* `description` - Show description shown in podcast apps (required)
* `author` - Your name or organization (required)
* `email` - Contact email (required by podcast directories)
* `category` - Podcast category: News, Technology, Business, etc. (required)
* `artwork` - Cover image URL, must be 1400x1400 to 3000x3000 pixels, JPG or PNG (required)
* `voice` - Piper TTS voice model (required)
* `duration` - Estimated episode duration in seconds, "600" = 10 minutes (required)
* `feeds` - Array of RSS feed URLs to monitor (required)
* `keywords` - Array of topic keywords for AI content selection (required)

**Available Piper Voices:**

* `en_US-ryan-high` - Deep, authoritative male voice
* `en_US-amy-medium` - Energetic female voice
* `en_US-lessac-medium` - Neutral, clear voice
* `en_GB-alan-medium` - British male voice

See all voices at: <https://rhasspy.github.io/piper-samples/>

## Local Development & Testing

Test the script generation and audio pipeline locally before deploying to the cloud.

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/lazy-podinator.git
cd lazy-podinator
```

### 2. Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file with your API key:

```bash
export ANTHROPIC_API_KEY="your-anthropic-api-key"
export PROJECT_ID="local-testing"  # Not needed for local testing
export BUCKET_NAME="local-testing"  # Not needed for local testing
```

Load the environment:

```bash
source .env
```

### 4. Test Script Generation (No Audio)

Run the test script to generate podcast scripts without audio:

```bash
python test/test_local.py
```

This creates:

* `output/scripts.json` - All scripts in JSON format
* `output/stablecoin_script.txt` - Individual text files per show
* `output/ai_script.txt`

Review the scripts to ensure Claude is selecting relevant topics.

### 5. Test Audio Generation with Docker

Docker is recommended for testing Piper TTS locally (matches production environment):

```bash
# Make script executable
chmod +x test/test_audio_docker.sh

# Generate audio files
./test/test_audio_docker.sh
```

This builds a Docker image with Piper TTS and generates MP3 files in `output/`.

Play the generated podcasts:

```bash
afplay output/stablecoin_podcast.mp3  # macOS
mpg123 output/stablecoin_podcast.mp3  # Linux
```

### 6. Test Audio with macOS Native (Alternative)

For quick testing on macOS without Docker:

```bash
chmod +x test/test_audio_macos.sh
./test/test_audio_macos.sh
```

**Note:** This uses macOS `say` command (not Piper), so voices won't match production.

### 7. Test Automatic Cleanup (Optional)

To verify that the 30-day cleanup works correctly:

```bash
# Set up GCP credentials (if not already done)
export BUCKET_NAME="your-podcast-bucket-name"

# Run cleanup test
python test/test_cleanup.py
```

This script will:

1. Create test episodes with dates ranging from 5 to 60 days old
2. Run the cleanup function
3. Verify that only episodes older than 30 days are deleted
4. Clean up all test data

Expected output:

```text
✅ SUCCESS: Cleanup working correctly!
   Expected 3 episodes remaining, found 3
```

---

## Google Cloud Run Deployment

Deploy to Google Cloud Platform for automated daily podcast generation.

### GCP Prerequisites

* **Google Cloud Platform Account** (Free Tier is sufficient)
* **Google Cloud CLI (`gcloud`)** installed and authenticated
* **Anthropic API Key** from [console.anthropic.com](https://console.anthropic.com/)

### 1. Enable Required APIs

```bash
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable artifactregistry.googleapis.com
```

### 2. Configure Deployment Script

Edit `scripts/deploy.sh` and set your values:

```bash
PROJECT_ID="your-google-cloud-project-id"
BUCKET_NAME="your-podcast-bucket-name"
ANTHROPIC_API_KEY="your-anthropic-api-key"
```

### 3. Create Storage Bucket (Public)

```bash
# Create bucket
gcloud storage buckets create gs://YOUR_BUCKET_NAME --location=us-central1

# Make bucket publicly readable (required for podcast apps)
gcloud storage buckets add-iam-policy-binding gs://YOUR_BUCKET_NAME \
    --member=allUsers \
    --role=roles/storage.objectViewer
```

### 4. Create Podcast Artwork

Generate cover art (1400x1400 to 3000x3000 pixels) and save to `artwork/` directory:

**Required files:**

* `artwork/stablecoin.jpg` - For "The Stablecoin Ledger"
* `artwork/ai.jpg` - For "AI Morning Brief"

**Free AI tools to generate artwork:**

* [Bing Image Creator](https://www.bing.com/create) (DALL-E 3, free)
* [Leonardo.ai](https://leonardo.ai) (150 credits/day)
* [Adobe Firefly](https://firefly.adobe.com) (25 credits/month)

See [artwork/README.md](artwork/README.md) for detailed instructions and example prompts.

**Note:** The deploy script will automatically upload artwork files to your GCS bucket.

### 5. Deploy to Cloud Run

```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

This builds the Docker container (with Piper TTS baked in) and deploys to Cloud Run.

Deployment takes 3-5 minutes. You'll see a service URL when complete.

### 6. Set Up Daily Trigger

Create a Cloud Scheduler job to run at 8:00 AM EST daily:

```bash
gcloud scheduler jobs create http daily-pod-trigger \
    --schedule="0 13 * * *" \
    --uri="$(gcloud run services describe lazy-podinator --region=us-central1 --format='value(status.url)')" \
    --http-method=GET \
    --location=us-central1
```

**Note:** `0 13 * * *` = 8:00 AM EST (13:00 UTC). Adjust for your timezone.

### 7. Test the Deployment

Trigger manually to test:

```bash
gcloud scheduler jobs run daily-pod-trigger --location=us-central1
```

Check Cloud Run logs:

```bash
gcloud run services logs read lazy-podinator --region=us-central1 --limit=100
```

### 8. Updating Configuration (No Redeploy Required!)

The configuration is stored in GCS and can be updated without rebuilding/redeploying:

**To update feeds, keywords, or show settings:**

```bash
# 1. Edit shows_config.json locally
vim shows_config.json

# 2. Upload to GCS (takes 2 seconds)
./scripts/update_config.sh

# Or manually:
gcloud storage cp shows_config.json gs://YOUR_BUCKET_NAME/config/
```

Changes take effect on the next scheduled run (8:00 AM EST) or trigger immediately:

```bash
gcloud scheduler jobs run daily-pod-trigger --location=us-central1
```

**Note:** Only redeploy (`./scripts/deploy.sh`) when you:

* Change Python code
* Update dependencies
* Modify Dockerfile or infrastructure

## Listen on Spotify & Podcast Apps

After your first episode generates, RSS feeds are available at:

```text
https://storage.googleapis.com/YOUR_BUCKET/stablecoin/feed.xml
https://storage.googleapis.com/YOUR_BUCKET/ai/feed.xml
```

### Live Shows

**AI Technology Morning Brief** - [Listen on Spotify](https://open.spotify.com/show/6ltJZXfvr5ZeSavapFO056)

**The Stablecoin Ledger** - [Listen on Spotify](https://open.spotify.com/show/5HxDtAnJk9FNCWVyQw8cmh)

### Submit to Spotify

1. Go to [Spotify for Podcasters](https://podcasters.spotify.com)
2. Click "Get Started" → "Add your podcast"
3. Paste your RSS feed URL
4. Verify ownership and submit

Spotify will automatically pull new episodes daily.

### Submit to Apple Podcasts

1. Go to [Apple Podcasts Connect](https://podcastsconnect.apple.com)
2. Sign in with your Apple ID
3. Click "+" → "New Show" → "Add a show with an RSS feed"
4. Paste your RSS feed URL

### Other Podcast Apps

Most podcast apps support adding custom RSS feeds:

* **Pocket Casts:** Search → "Submit RSS"
* **Overcast:** Add URL → paste feed
* **Google Podcasts:** Paste URL in search
* **Any podcast app:** Look for "Add by URL" or "Add RSS feed"

## Cost & Storage Management

This setup is designed to run within GCP's free tier:

* **Cloud Run:** 2 million requests/month free
* **Cloud Storage:** 5GB free
* **Cloud Scheduler:** 3 jobs free
* **Anthropic API:** Pay-per-use (very low cost for daily podcasts)
* **Gmail API:** Free (15 billion quota units/day)
* **Piper TTS:** Free and open-source
* **Spotify/Apple:** Free to submit

**Automatic Cleanup:** The system automatically deletes podcast episodes older than 30 days to prevent storage buildup. RSS feeds only display episodes from the last 30 days. This keeps storage usage minimal and well within the free tier limits.

**Estimated Monthly Cost:**

* **Anthropic API:** ~$0.50-$2.00/month (depends on article length and number of shows)
* **Everything else:** $0 (within free tier)
