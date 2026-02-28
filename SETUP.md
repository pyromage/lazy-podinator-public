# Setup Guide for Personal Use

Follow these steps to set up Lazy Podinator for your personal podcasts.

## Quick Setup

### 1. Create Your Personal Configuration

```bash
# Copy example files to create your personal configs
cp shows_config.example.json shows_config.local.json
cp .env.example .env

# Optional: Custom pronunciations
cp pronunciation_guide.json pronunciation_guide.local.json
```

### 2. Edit Your Show Configuration

Edit `shows_config.local.json`:

- Change show keys (e.g., `my_topic_1` → `tech_daily`)
- Update titles, descriptions, and author info
- Add your email address
- Replace RSS feeds with your preferred sources  
- Update keywords for your interests
- Set artwork URLs (point to your GCP bucket)

### 3. Set Up Environment Variables

Edit `.env`:

```bash
export ANTHROPIC_API_KEY="your-actual-key"
export PROJECT_ID="your-gcp-project"
export BUCKET_NAME="your-bucket-name"
```

### 4. Test Locally

```bash
# Generate scripts (no audio)
python test/test_local.py

# Test audio with Docker (recommended)
chmod +x test/test_audio_docker.sh
./test/test_audio_docker.sh
```

### 5. Deploy to Google Cloud

```bash
chmod +x scripts/deploy.sh
source .env
./scripts/deploy.sh
```

## File Precedence

The system checks files in this order:

1. **Local files** (private, not in git):
   - `shows_config.local.json`
   - `pronunciation_guide.local.json`
   - `.env`

2. **Example files** (public, safe defaults):
   - `shows_config.example.json` 
   - `pronunciation_guide.json`

3. **Original files** (fallback):
   - `shows_config.json`

## Updating Configuration

```bash
# Update cloud config without redeploying
./scripts/update_config.sh
```

This uploads your local configs to Google Cloud Storage.

## Git Workflow

Your personal configs are automatically ignored by git:

```bash
git status
# Will NOT show:
# - shows_config.local.json
# - pronunciation_guide.local.json  
# - .env
```

Only example/template files are tracked in the repository.