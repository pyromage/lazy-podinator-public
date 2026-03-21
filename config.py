"""Shared configuration, clients, and state management."""

import os
import json
from datetime import datetime, timedelta
from google.cloud import storage
import anthropic


# Initialize Clients
anthropic_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
storage_client = storage.Client()
BUCKET_NAME = os.environ.get("BUCKET_NAME")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
GMAIL_ENABLED = os.environ.get("GMAIL_ENABLED", "").lower() == "true"

# Piper configuration
PIPER_PATH = "/app/piper/piper"
MODELS_PATH = "/app/piper/models"


def load_json_config(filename):
    """Load configuration from GCS or local file (with fallback)"""
    if BUCKET_NAME and BUCKET_NAME != "local-testing":
        try:
            print(f"Loading {filename} from GCS bucket: {BUCKET_NAME}")
            bucket = storage_client.bucket(BUCKET_NAME)
            blob = bucket.blob(f"config/{filename}")
            config_json = blob.download_as_text()
            print(f"✓ Loaded {filename} from GCS")
            return json.loads(config_json)
        except Exception as e:
            print(f"Warning: Could not load {filename} from GCS: {e}")
            print(f"Falling back to local {filename}")

    config_path = os.path.join(os.path.dirname(__file__), filename)
    with open(config_path, 'r') as f:
        return json.load(f)


SHOWS = load_json_config('shows_config.json')


def load_article_history():
    """Load previously covered article URLs from GCS."""
    if not BUCKET_NAME or BUCKET_NAME == "local-testing":
        return {"covered_urls": {}}
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob("config/article_history.json")
        history = json.loads(blob.download_as_text())
        cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        history["covered_urls"] = {
            url: date_str
            for url, date_str in history.get("covered_urls", {}).items()
            if date_str >= cutoff
        }
        print(f"Loaded article history: {len(history['covered_urls'])} previously covered URLs")
        return history
    except Exception:
        print("No article history found (starting fresh)")
        return {"covered_urls": {}}


def save_article_history(history, new_urls):
    """Save updated article history to GCS after successful pipeline run."""
    if not BUCKET_NAME or BUCKET_NAME == "local-testing":
        return
    today = datetime.now().strftime('%Y-%m-%d')
    for url in new_urls:
        history["covered_urls"][url] = today
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob("config/article_history.json")
        blob.upload_from_string(json.dumps(history), content_type="application/json")
        print(f"Article history saved: {len(history['covered_urls'])} total URLs tracked")
    except Exception as e:
        print(f"WARNING: Could not save article history: {e}")
