import os
import json
import subprocess
import tempfile
import time
import feedparser
import anthropic
import requests
from google.cloud import storage
from datetime import datetime, timedelta
from email.utils import formatdate
from flask import Flask, jsonify
from bs4 import BeautifulSoup
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

# Initialize Flask app for Cloud Run
app = Flask(__name__)

# Initialize Clients
anthropic_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
storage_client = storage.Client()
BUCKET_NAME = os.environ.get("BUCKET_NAME")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
GMAIL_ENABLED = os.environ.get("GMAIL_ENABLED", "").lower() == "true"

# Piper configuration
PIPER_PATH = "/app/piper/piper"
MODELS_PATH = "/app/piper/models"

# Load configuration from external JSON files
def load_json_config(filename):
    """Load configuration from GCS or local file (with fallback)"""
    # Try loading from GCS first (for production)
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

    # Fallback to local file (for development/testing)
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

# Pronunciation guide for TTS
_pronunciation_guide = None

def load_pronunciation_guide():
    """Load pronunciation guide (cached after first load)"""
    global _pronunciation_guide
    if _pronunciation_guide is None:
        try:
            _pronunciation_guide = load_json_config('pronunciation_guide.json')
        except Exception as e:
            print(f"Warning: Could not load pronunciation guide: {e}")
            _pronunciation_guide = {"acronyms": {}, "proper_nouns": {}, "technical_terms": {}}
    return _pronunciation_guide

def apply_pronunciation_fixes(text, show_key=None):
    """Replace difficult words with TTS-friendly respellings before Piper TTS."""
    import re
    guide = load_pronunciation_guide()

    # Acronyms and proper nouns: case-sensitive whole-word match
    for category in ['acronyms', 'proper_nouns']:
        for word, respelling in guide.get(category, {}).items():
            pattern = r'\b' + re.escape(word) + r'\b'
            text = re.sub(pattern, respelling, text)

    # Technical terms: case-insensitive whole-word match
    for word, respelling in guide.get('technical_terms', {}).items():
        pattern = r'\b' + re.escape(word) + r'\b'
        text = re.sub(pattern, respelling, text, flags=re.IGNORECASE)

    return text

def normalize_for_tts(text):
    """Normalize Unicode text for TTS: convert fancy Unicode letters to ASCII, strip emojis/symbols."""
    import re
    import unicodedata

    # Strip lone surrogates (invalid Unicode that can't be normalized)
    text = text.encode('utf-8', errors='ignore').decode('utf-8')
    # NFKD converts mathematical bold/italic/script letters (𝐓𝐡𝐞, 𝗦𝗧𝗔) to their ASCII base forms
    text = unicodedata.normalize('NFKD', text)

    result = []
    for ch in text:
        cat = unicodedata.category(ch)
        # Keep letters, numbers, punctuation, separators, and common whitespace
        if cat[0] in ('L', 'N', 'P', 'Z') or ch in ('\n', '\t'):
            result.append(ch)
        else:
            # Replace symbols, emojis, combining marks leftover, control chars with space
            result.append(' ')

    text = ''.join(result)
    # Collapse multiple spaces / blank lines
    text = re.sub(r'  +', ' ', text).strip()
    return text


def fetch_linkedin_top_content(urls):
    """Fetch posts from LinkedIn top-content pages via JSON-LD structured data"""
    articles = []
    print("Fetching LinkedIn top-content pages...")

    for url in urls:
        try:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            soup = BeautifulSoup(response.content, 'html.parser')

            for tag in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(tag.string)
                    # CollectionPage wraps posts in mainEntity or hasPart
                    posts = []
                    if isinstance(data, dict):
                        if data.get('@type') == 'CollectionPage':
                            posts = data.get('hasPart', data.get('mainEntity', {}).get('itemListElement', []))
                        elif data.get('@type') == 'ItemList':
                            posts = data.get('itemListElement', [])

                    for item in posts:
                        post = item.get('item', item) if isinstance(item, dict) else item
                        text = post.get('articleBody') or post.get('text', '')
                        if not text:
                            continue
                        text = normalize_for_tts(text)
                        author = post.get('author', {})
                        author_name = author.get('name', 'LinkedIn') if isinstance(author, dict) else 'LinkedIn'
                        articles.append({
                            "title": f"{author_name}: {text[:80].strip()}...",
                            "link": post.get('url', url),
                            "snippet": text[:200],
                            "source": "linkedin"
                        })
                except (json.JSONDecodeError, AttributeError):
                    continue

            print(f"  {url}: {len([a for a in articles if a.get('source') == 'linkedin'])} posts")
        except Exception as e:
            print(f"Failed to fetch LinkedIn top-content {url}: {e}")

    return articles


def fetch_gmail_content(label_names):
    """Fetch newsletter content from Gmail messages with specified labels (last 7 days)."""
    import base64

    articles = []
    try:
        service = get_gmail_service()
    except Exception as e:
        print(f"WARNING: Could not connect to Gmail: {e}")
        return articles

    # Resolve label names to IDs
    try:
        labels_response = service.users().labels().list(userId='me').execute()
        label_map = {lbl['name']: lbl['id'] for lbl in labels_response.get('labels', [])}
    except Exception as e:
        print(f"WARNING: Could not list Gmail labels: {e}")
        return articles

    label_ids = []
    for name in label_names:
        if name in label_map:
            label_ids.append(label_map[name])
        else:
            print(f"  WARNING: Gmail label '{name}' not found, skipping")

    if not label_ids:
        return articles

    # Collect unique message IDs across all labels
    msg_ids = set()
    for label_id in label_ids:
        try:
            response = service.users().messages().list(
                userId='me', labelIds=[label_id], q='newer_than:1d'
            ).execute()
            for msg in response.get('messages', []):
                msg_ids.add(msg['id'])
            # Handle pagination
            while response.get('nextPageToken'):
                response = service.users().messages().list(
                    userId='me', labelIds=[label_id], q='newer_than:1d',
                    pageToken=response['nextPageToken']
                ).execute()
                for msg in response.get('messages', []):
                    msg_ids.add(msg['id'])
        except Exception as e:
            print(f"  WARNING: Could not list messages for label {label_id}: {e}")

    print(f"  Found {len(msg_ids)} emails from last 7 days")

    # Fetch each message
    for msg_id in msg_ids:
        try:
            msg = service.users().messages().get(
                userId='me', id=msg_id, format='full'
            ).execute()

            # Extract headers
            headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
            subject = headers.get('Subject', '(no subject)')

            # Extract body
            body_text = _extract_email_body(msg['payload'], base64)
            if not body_text:
                continue

            articles.append({
                "title": subject,
                "link": f"https://mail.google.com/mail/u/0/#inbox/{msg_id}",
                "snippet": body_text[:300],
                "source": "email",
                "full_text": body_text[:3000]
            })
        except Exception as e:
            print(f"  WARNING: Could not fetch message {msg_id}: {e}")

    print(f"  Extracted {len(articles)} newsletter articles from Gmail")
    return articles


def _extract_email_body(payload, base64_mod):
    """Recursively extract text content from Gmail message payload."""
    mime = payload.get('mimeType', '')

    if mime == 'text/plain' and payload.get('body', {}).get('data'):
        return base64_mod.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')

    parts = payload.get('parts', [])
    plain_text = None
    html_text = None
    for part in parts:
        part_mime = part.get('mimeType', '')
        if part_mime == 'text/plain' and part.get('body', {}).get('data'):
            plain_text = base64_mod.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
        elif part_mime == 'text/html' and part.get('body', {}).get('data'):
            html_text = base64_mod.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
        elif part_mime.startswith('multipart/'):
            result = _extract_email_body(part, base64_mod)
            if result:
                return result

    if plain_text:
        return plain_text
    if html_text:
        soup = BeautifulSoup(html_text, 'html.parser')
        return soup.get_text(separator='\n', strip=True)
    return ""


def fetch_rss_feeds(feed_urls):
    """Fetch articles from RSS feeds, filtering to last 7 days"""
    from time import mktime
    articles = []
    cutoff_date = datetime.now() - timedelta(days=7)
    print("Fetching RSS feeds...")

    for url in feed_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                entry_date = None
                for date_field in ('published_parsed', 'updated_parsed'):
                    parsed = entry.get(date_field)
                    if parsed:
                        entry_date = datetime.fromtimestamp(mktime(parsed))
                        break
                if entry_date and entry_date < cutoff_date:
                    continue
                articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "snippet": entry.get('summary', '')[:200],
                    "source": "rss"
                })
        except Exception as e:
            print(f"Failed to parse {url}: {e}")

    return articles

def fetch_news(article_history=None):
    """Ingests news from RSS feeds, with optional deduplication against history"""
    articles = []

    # Aggregate feeds from all shows
    all_feeds = set()
    all_linkedin = set()

    for show_key, config in SHOWS.items():
        feeds = config.get('feeds', [])
        all_feeds.update(feeds)
        linkedin_urls = config.get('linkedin_top_content', [])
        all_linkedin.update(linkedin_urls)

    # Fetch from RSS feeds (deduplicated across shows)
    if all_feeds:
        print(f"Fetching from {len(all_feeds)} unique RSS feeds...")
        articles.extend(fetch_rss_feeds(list(all_feeds)))

    # Fetch from LinkedIn top-content pages (deduplicated across shows)
    if all_linkedin:
        print(f"Fetching from {len(all_linkedin)} LinkedIn top-content pages...")
        articles.extend(fetch_linkedin_top_content(list(all_linkedin)))

    # Fetch from Gmail newsletters (if enabled)
    if GMAIL_ENABLED:
        all_gmail_labels = set()
        for config in SHOWS.values():
            all_gmail_labels.update(config.get('gmail_labels', []))
        if all_gmail_labels:
            print(f"Fetching from {len(all_gmail_labels)} Gmail labels...")
            articles.extend(fetch_gmail_content(list(all_gmail_labels)))

    print(f"Total articles fetched: {len(articles)}")

    # Remove previously covered articles
    if article_history and article_history.get("covered_urls"):
        covered = article_history["covered_urls"]
        before_count = len(articles)
        articles = [a for a in articles if a.get("link") not in covered]
        filtered_count = before_count - len(articles)
        if filtered_count > 0:
            print(f"Filtered out {filtered_count} previously covered articles")
        print(f"Total articles after filtering: {len(articles)}")

    return articles

def fetch_article_content(url):
    """Fetch full article content from URL"""
    try:
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        soup = BeautifulSoup(response.content, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "aside"]):
            script.decompose()

        # Try to find article content (common patterns)
        article_content = None
        for selector in ['article', '.article-content', '.post-content', 'main', '.entry-content']:
            article_content = soup.select_one(selector)
            if article_content:
                break

        if article_content:
            text = article_content.get_text(separator='\n', strip=True)
        else:
            # Fallback to body
            text = soup.get_text(separator='\n', strip=True)

        # Clean up: remove extra whitespace and limit length
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n'.join(lines)

        # Limit to first 3000 characters to avoid token limits
        return text[:3000] if text else ""

    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def call_claude_with_retry(max_retries=3, **kwargs):
    """Call Claude API with exponential backoff for transient errors.
    Billing errors are surfaced immediately without retrying."""
    for attempt in range(max_retries + 1):
        try:
            return anthropic_client.messages.create(**kwargs)
        except anthropic.BadRequestError as e:
            if "credit balance is too low" in str(e):
                print("BILLING ERROR: Anthropic API credits depleted. "
                      "Top up at console.anthropic.com/settings/billing")
                send_failure_notification(
                    subject="[Lazy Podinator] API credits depleted",
                    body="The Anthropic API credit balance is too low. "
                         "Please top up at console.anthropic.com/settings/billing.\n\n"
                         f"Error: {e}"
                )
            raise
        except (anthropic.RateLimitError, anthropic.APIStatusError,
                anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt  # 1s, 2s, 4s
            print(f"API error (attempt {attempt+1}/{max_retries+1}): {e}. Retrying in {wait}s...")
            time.sleep(wait)


def get_gmail_service():
    """Load Gmail OAuth token from GCS and return an authenticated Gmail API service."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    blob = storage_client.bucket(BUCKET_NAME).blob("config/gmail_token.json")
    token_data = json.loads(blob.download_as_string())

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes"),
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_data.update({
            "token": creds.token,
            "refresh_token": creds.refresh_token,
        })
        blob.upload_from_string(json.dumps(token_data), content_type="application/json")

    return build("gmail", "v1", credentials=creds)


def send_failure_notification(subject, body):
    """Send a failure alert email via Gmail API. Silently skips if not configured."""
    import base64
    from email.mime.text import MIMEText

    email = os.environ.get("NOTIFY_EMAIL")
    if not email:
        return

    try:
        service = get_gmail_service()
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = email
        msg["To"] = email
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"Failure notification sent to {email}")
    except Exception as e:
        print(f"WARNING: Could not send failure notification: {e}")


def select_articles(articles):
    """First pass: Claude selects the most interesting articles for each show"""

    # Build dynamic show descriptions from config
    show_list = []
    for key, config in SHOWS.items():
        keywords = ", ".join(config.get('keywords', []))
        interests = config.get('interests', [])
        desc = f"- '{config['title']}' (key: {key}, Focus: {keywords})"
        if interests:
            interests_str = "; ".join(interests)
            desc += f"\n      Prioritize: {interests_str}"
        show_list.append(desc)

    shows_description = "\n    ".join(show_list)

    selection_prompt = f"""You are the Executive Producer of a media network. You run the following daily shows:
    {shows_description}

    Your Task:
    1. Analyze the provided news headlines and snippets.
    2. For EACH show, select up to 20 of the most relevant and interesting article URLs.
    3. Return ONLY the URLs that are worth covering, grouped by show.

    Selection Criteria - PRIORITIZE stories about:
    - Market-moving developments: significant funding rounds, major earnings, price movements
    - New product launches and first-of-their-kind innovations
    - Mergers, acquisitions, and strategic partnerships that reshape markets
    - Technology breakthroughs: new capabilities, research milestones
    - Regulatory changes with broad industry impact
    - Each show also has its own priority criteria listed above — follow those

    DEPRIORITIZE or SKIP:
    - Opinion pieces and editorials (unless from a highly notable figure)
    - Listicles ("Top 10...", "Best of...")
    - Minor product updates or incremental version bumps
    - Duplicate coverage of the same story from multiple sources (pick the best source)
    - Promotional content or sponsored articles

    Return JSON format with keys matching the show keys (e.g., "stablecoin", "ai").
    Each value should be an array of URLs (strings) for that show.
    Example: {{"stablecoin": ["url1", "url2", ...], "ai": ["url3", "url4", ...]}}
    Do not include any text before or after the JSON object."""

    print("Step 1: Selecting top articles...")
    response = call_claude_with_retry(
        model=CLAUDE_MODEL,
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": f"{selection_prompt}\n\nHeadlines:\n{json.dumps(articles)}"
            }
        ]
    )

    response_text = response.content[0].text
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        import re
        # Strip markdown code fences if present
        cleaned = re.sub(r'^```(?:json)?\s*', '', response_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        else:
            print(f"ERROR: Could not parse selection response. Raw response:\n{response_text[:500]}")
            return {}

def generate_scripts(selected_urls, all_articles=None):
    """Second pass: Generate podcast scripts from full article content"""

    # Build lookup for pre-fetched content (e.g., email articles)
    prefetched = {}
    if all_articles:
        for article in all_articles:
            if article.get("full_text"):
                prefetched[article["link"]] = article["full_text"]

    # Fetch full content for selected articles
    print("Step 2: Fetching full article content...")
    articles_by_show = {}

    for show_key, urls in selected_urls.items():
        articles_by_show[show_key] = []
        config = SHOWS.get(show_key, {})
        print(f"  {config.get('title', show_key)}: Fetching {len(urls)} articles...")

        for url in urls[:20]:  # Limit to 20 articles max
            content = prefetched.get(url) or fetch_article_content(url)
            if content:
                articles_by_show[show_key].append({
                    "url": url,
                    "content": content
                })

    # Build dynamic show descriptions from config
    show_list = []
    script_keys = []
    for key, config in SHOWS.items():
        keywords = ", ".join(config.get('keywords', []))
        show_list.append(f"- '{config['title']}' (Focus: {keywords})")
        script_keys.append(f'"{key}_script"')

    shows_description = "\n    ".join(show_list)
    keys_description = ", ".join(script_keys)

    system_prompt = f"""You are the Executive Producer of a media network. You run the following daily shows:
    {shows_description}

    Your Task:
    1. For EACH show, you have been provided with full article content.
    2. Write a DETAILED 30-SECOND DISCUSSION for each article (approximately 75-90 words per topic).
       - Tone: Conversational, natural speech - like a real radio host, not a news anchor
       - Use contractions (it's, we're, that's) and natural phrasing
       - Each topic must include:
         * The key facts and what happened
         * Why it matters and the implications
         * Relevant context, numbers, or quotes from the article
         * Market impact, trends, or industry significance
       - NO generic statements like "In conclusion" or "This is important"
       - NO brief 1-2 sentence summaries - each topic needs FULL 30-second treatment
       - Example: "Here's something interesting - PayPal just acquired Cymbio, and this one's all about AI-powered shopping. Cymbio's got this marketplace automation platform that lets merchants sell through AI assistants like Microsoft Copilot and Perplexity. We're talking about conversational AI that's basically becoming the new storefront. The deal gives PayPal access to Cymbio's automated product feeds across more than 500 marketplaces. So they're positioning themselves ahead of traditional payment processors in what's being called agentic commerce."
    3. Aggregate all topic summaries into a single podcast script for each show.
       - Start with a natural welcome (1-2 sentences) - sound like a radio host, not a robot
       - After EACH topic, add a clear pause marker: "... [PAUSE] ..."
       - Use smooth transitions: "Next up...", "Meanwhile...", "In other news...", "Moving on...", "Here's an interesting one..."
       - Each show should have approximately 20 topics with 30 seconds each = ~10 minutes total
       - End with a brief, natural sign-off (1 sentence)

    CRITICAL FORMATTING:
    - Each topic must be 75-90 words
    - After every single topic, include "... [PAUSE] ..." on its own line to create a 2-second break
    - Use natural, conversational language with contractions

    PRONUNCIATION FOR TEXT-TO-SPEECH:
    These scripts will be read aloud by a text-to-speech engine. To ensure correct pronunciation:
    - Spell out acronyms with periods between letters: USDC -> "U.S.D.C.", CBDC -> "C.B.D.C.", LLM -> "L.L.M.", ESA -> "E.S.A.", FSDP -> "F.S.D.P."
    - Exception for acronyms commonly pronounced as words: NASA, JAXA, ISRO stay as-is
    - Write "xAI" as "ex A.I." and "GenAI" as "Jen A.I."
    - Avoid leaving bare acronyms that a TTS engine might try to pronounce as a single word

    Return JSON format only with keys: {keys_description}
    Each value should be the complete podcast script for that show.
    Do not include any text before or after the JSON object."""

    print("Step 3: Generating podcast scripts...")
    response = call_claude_with_retry(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        messages=[
            {
                "role": "user",
                "content": f"{system_prompt}\n\nArticles by Show:\n{json.dumps(articles_by_show)}"
            }
        ]
    )

    # Extract JSON from response
    response_text = response.content[0].text

    # Try to find JSON in the response (sometimes Claude adds explanation text)
    try:
        # First, try to parse directly
        return json.loads(response_text)
    except json.JSONDecodeError:
        # Look for JSON object in the text
        import re
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        else:
            print(f"ERROR: Could not find JSON in response: {response_text[:500]}")
            raise

def generate_audio(script_text, voice_model, show_key=None):
    """Converts text to WAV using Piper TTS, then to MP3 with natural pacing"""
    model_path = os.path.join(MODELS_PATH, f"{voice_model}.onnx")
    config_path = os.path.join(MODELS_PATH, f"{voice_model}.onnx.json")

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file:
        wav_path = wav_file.name

    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as mp3_file:
        mp3_path = mp3_file.name

    try:
        # Remove [PAUSE] markers - we'll handle pauses with sentence silence
        cleaned_text = script_text.replace("[PAUSE]", "").replace("...", ".")

        # Apply pronunciation fixes for TTS
        cleaned_text = apply_pronunciation_fixes(cleaned_text, show_key=show_key)

        # Run Piper to generate WAV with improved parameters for natural speech
        process = subprocess.run(
            [
                PIPER_PATH,
                "--model", model_path,
                "--config", config_path,
                "--length-scale", "1.1",  # Slightly slower for more natural pacing (default is 1.0)
                "--sentence-silence", "0.8",  # 800ms pause between sentences (default is 0.2)
                "--output_file", wav_path
            ],
            input=cleaned_text.encode('utf-8'),
            capture_output=True,
            check=True
        )
        print(f"Piper output: {process.stderr.decode()}")

        # Convert WAV to MP3 using ffmpeg with audio normalization for better quality
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", wav_path,
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",  # Normalize audio levels
                "-codec:a", "libmp3lame",
                "-qscale:a", "2",  # High quality MP3
                mp3_path
            ],
            capture_output=True,
            check=True
        )

        with open(mp3_path, 'rb') as f:
            return f.read()
    finally:
        # Cleanup temp files
        if os.path.exists(wav_path):
            os.unlink(wav_path)
        if os.path.exists(mp3_path):
            os.unlink(mp3_path)

def upload_to_bucket(audio_bytes, show_key):
    """Uploads MP3 to Google Cloud Storage and returns public URL"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f"{show_key}/{date_str}_update.mp3"

    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)

    blob.upload_from_string(audio_bytes, content_type="audio/mpeg")

    # Return the public URL
    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
    return public_url

def cleanup_old_episodes(show_key, days_to_keep=30):
    """Delete podcast episodes older than specified days from GCS"""
    bucket = storage_client.bucket(BUCKET_NAME)
    blobs = bucket.list_blobs(prefix=f"{show_key}/")

    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    deleted_count = 0

    for blob in blobs:
        if blob.name.endswith('.mp3'):
            # Extract date from filename (format: show_key/YYYY-MM-DD_update.mp3)
            filename = blob.name.split('/')[-1]
            date_str = filename.replace('_update.mp3', '')
            try:
                ep_date = datetime.strptime(date_str, '%Y-%m-%d')
                if ep_date < cutoff_date:
                    print(f"Deleting old episode: {blob.name} (age: {(datetime.now() - ep_date).days} days)")
                    blob.delete()
                    deleted_count += 1
            except ValueError:
                continue

    if deleted_count > 0:
        print(f"Cleaned up {deleted_count} episodes older than {days_to_keep} days for {show_key}")

    return deleted_count

def get_existing_episodes(show_key):
    """Get list of existing episodes from GCS bucket (last 30 days only)"""
    bucket = storage_client.bucket(BUCKET_NAME)
    blobs = bucket.list_blobs(prefix=f"{show_key}/")

    cutoff_date = datetime.now() - timedelta(days=30)
    episodes = []

    for blob in blobs:
        if blob.name.endswith('.mp3'):
            # Extract date from filename (format: show_key/YYYY-MM-DD_update.mp3)
            filename = blob.name.split('/')[-1]
            date_str = filename.replace('_update.mp3', '')
            try:
                ep_date = datetime.strptime(date_str, '%Y-%m-%d')
                # Only include episodes from last 30 days
                if ep_date >= cutoff_date:
                    episodes.append({
                        'date': ep_date,
                        'url': f"https://storage.googleapis.com/{BUCKET_NAME}/{blob.name}",
                        'size': blob.size or 0
                    })
            except ValueError:
                continue

    # Sort by date, newest first
    episodes.sort(key=lambda x: x['date'], reverse=True)
    return episodes

def generate_podcast_rss(show_key, config):
    """Generate podcast RSS feed XML for a show"""
    episodes = get_existing_episodes(show_key)

    # Create RSS structure with iTunes namespace
    rss = Element('rss')
    rss.set('version', '2.0')
    rss.set('xmlns:itunes', 'http://www.itunes.com/dtds/podcast-1.0.dtd')
    rss.set('xmlns:content', 'http://purl.org/rss/1.0/modules/content/')

    channel = SubElement(rss, 'channel')

    # Required channel elements
    SubElement(channel, 'title').text = config['title']
    SubElement(channel, 'link').text = f"https://storage.googleapis.com/{BUCKET_NAME}/{show_key}/feed.xml"
    SubElement(channel, 'language').text = 'en-us'
    SubElement(channel, 'description').text = config.get('description', f"Daily {config['title']} podcast")

    # iTunes-specific tags (required for Spotify)
    SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}author').text = config.get('author', 'Lazy Podinator')
    SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}summary').text = config.get('description', f"Daily {config['title']} podcast")
    SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit').text = 'false'

    # Category
    category = SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}category')
    category.set('text', config.get('category', 'News'))

    # Artwork (required for Spotify - must be 1400x1400 to 3000x3000)
    if config.get('artwork'):
        image = SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}image')
        image.set('href', config['artwork'])

    # Owner info
    owner = SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}owner')
    SubElement(owner, '{http://www.itunes.com/dtds/podcast-1.0.dtd}name').text = config.get('author', 'Lazy Podinator')
    SubElement(owner, '{http://www.itunes.com/dtds/podcast-1.0.dtd}email').text = config.get('email', 'podcast@example.com')

    # Add episodes
    for ep in episodes:
        item = SubElement(channel, 'item')
        ep_title = f"{config['title']} - {ep['date'].strftime('%B %d, %Y')}"
        SubElement(item, 'title').text = ep_title
        SubElement(item, 'description').text = f"Daily update for {ep['date'].strftime('%B %d, %Y')}"
        SubElement(item, 'pubDate').text = formatdate(ep['date'].timestamp(), usegmt=True)
        SubElement(item, 'guid').text = ep['url']

        # Enclosure (the actual audio file)
        enclosure = SubElement(item, 'enclosure')
        enclosure.set('url', ep['url'])
        enclosure.set('type', 'audio/mpeg')
        enclosure.set('length', str(ep['size']))

        # iTunes episode tags
        SubElement(item, '{http://www.itunes.com/dtds/podcast-1.0.dtd}duration').text = config.get('duration', '120')
        SubElement(item, '{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit').text = 'false'

    # Pretty print XML
    xml_str = tostring(rss, encoding='unicode')
    parsed = minidom.parseString(xml_str)
    return parsed.toprettyxml(indent="  ")

def update_podcast_feeds():
    """Generate and upload RSS feeds for all shows"""
    feed_urls = {}

    for show_key, config in SHOWS.items():
        try:
            print(f"Generating RSS feed for {config['title']}...")
            rss_xml = generate_podcast_rss(show_key, config)

            # Upload feed to GCS
            bucket = storage_client.bucket(BUCKET_NAME)
            blob = bucket.blob(f"{show_key}/feed.xml")
            blob.upload_from_string(rss_xml, content_type="application/rss+xml")

            feed_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{show_key}/feed.xml"
            feed_urls[show_key] = feed_url
            print(f"RSS feed uploaded: {feed_url}")

        except Exception as e:
            print(f"Error generating feed for {show_key}: {e}")

    return feed_urls

@app.route('/', methods=['GET', 'POST'])
def daily_podcast_entrypoint():
    """The Cloud Run Entry Point"""
    try:
        # 0. Load article history for deduplication
        article_history = load_article_history()

        # 1. Ingest
        news_data = fetch_news(article_history=article_history)

        # 2. Select top articles
        selected_urls = select_articles(news_data)

        if not selected_urls:
            print("ERROR: Article selection returned empty — aborting pipeline")
            return jsonify({"error": "Article selection failed"}), 500

        # 3. Generate scripts from full content
        scripts_json = generate_scripts(selected_urls, all_articles=news_data)

        results = {}

        # 4. Generate audio in parallel (each show ~16 min sequentially)
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def produce_show(show_key, config):
            script_key = f"{show_key}_script"
            if script_key not in scripts_json:
                print(f"No script generated for {show_key}")
                return show_key, None
            print(f"Generating audio for {config['title']}...")
            audio_data = generate_audio(scripts_json[script_key], config['voice'], show_key=show_key)
            public_url = upload_to_bucket(audio_data, show_key)
            return show_key, public_url

        with ThreadPoolExecutor(max_workers=len(SHOWS)) as executor:
            futures = {
                executor.submit(produce_show, key, cfg): key
                for key, cfg in SHOWS.items()
            }
            for future in as_completed(futures):
                show_key, url = future.result()
                if url:
                    results[show_key] = url

        # 5. Cleanup old episodes (older than 30 days)
        print("Cleaning up episodes older than 30 days...")
        for show_key in SHOWS.keys():
            cleanup_old_episodes(show_key, days_to_keep=30)

        # 6. Update RSS feeds
        feed_urls = update_podcast_feeds()

        # 7. Save article history after successful completion
        all_covered_urls = []
        for urls in selected_urls.values():
            all_covered_urls.extend(urls)
        save_article_history(article_history, all_covered_urls)

        return jsonify({
            "status": "success",
            "podcasts": results,
            "feeds": feed_urls
        }), 200

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error occurred: {e}")
        print(f"Full traceback:\n{error_details}")
        send_failure_notification(
            subject="[Lazy Podinator] Pipeline failed",
            body=f"The daily podcast pipeline failed with the following error:\n\n{e}\n\n{error_details}"
        )
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
