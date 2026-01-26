import os
import json
import subprocess
import tempfile
import base64
import feedparser
import anthropic
import requests
from google.cloud import storage
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
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

# Piper configuration
PIPER_PATH = "/app/piper/piper"
MODELS_PATH = "/app/piper/models"

# Gmail API scopes
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

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

def get_gmail_service():
    """Initialize Gmail API service using stored credentials"""
    creds = None
    token_path = os.path.join(os.path.dirname(__file__), 'gmail_token.json')
    credentials_path = os.path.join(os.path.dirname(__file__), 'gmail_credentials.json')

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                print("Gmail credentials not found. Skipping email fetch.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def parse_email_content(html_content):
    """Extract headlines and summaries from newsletter HTML"""
    soup = BeautifulSoup(html_content, 'html.parser')

    articles = []

    # Look for common newsletter patterns (headlines in h1, h2, h3, strong, or links)
    for tag in soup.find_all(['h1', 'h2', 'h3']):
        text = tag.get_text(strip=True)
        if len(text) > 10 and len(text) < 200:
            # Try to get the next paragraph as snippet
            next_p = tag.find_next('p')
            snippet = next_p.get_text(strip=True)[:200] if next_p else ""

            # Try to find associated link
            link = tag.find('a')
            href = link.get('href', '') if link else ''

            articles.append({
                "title": text,
                "link": href,
                "snippet": snippet,
                "source": "email"
            })

    # Also look for bold/strong text that might be headlines
    if len(articles) < 3:
        for tag in soup.find_all('strong')[:10]:
            text = tag.get_text(strip=True)
            if len(text) > 20 and len(text) < 150:
                parent = tag.find_parent('p') or tag.find_parent('div')
                snippet = parent.get_text(strip=True)[:200] if parent else ""
                articles.append({
                    "title": text,
                    "link": "",
                    "snippet": snippet,
                    "source": "email"
                })

    return articles[:6]  # Limit to 6 articles per email

def fetch_emails(gmail_labels):
    """Fetch recent emails from specified Gmail labels"""
    articles = []

    if not gmail_labels:
        return articles

    service = get_gmail_service()
    if not service:
        return articles

    print(f"Fetching emails from labels: {gmail_labels}")

    for label_name in gmail_labels:
        try:
            # Get label ID from name
            labels_result = service.users().labels().list(userId='me').execute()
            label_id = None
            for label in labels_result.get('labels', []):
                if label['name'].lower() == label_name.lower():
                    label_id = label['id']
                    break

            if not label_id:
                print(f"Label '{label_name}' not found")
                continue

            # Get recent messages from this label (last 3 days)
            query = "newer_than:3d"
            results = service.users().messages().list(
                userId='me',
                labelIds=[label_id],
                q=query,
                maxResults=5
            ).execute()

            messages = results.get('messages', [])

            for msg in messages:
                msg_data = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='full'
                ).execute()

                # Get email subject
                headers = msg_data.get('payload', {}).get('headers', [])
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')

                # Get email body
                payload = msg_data.get('payload', {})
                body_html = ""

                if 'parts' in payload:
                    for part in payload['parts']:
                        if part.get('mimeType') == 'text/html':
                            body_data = part.get('body', {}).get('data', '')
                            body_html = base64.urlsafe_b64decode(body_data).decode('utf-8')
                            break
                elif payload.get('mimeType') == 'text/html':
                    body_data = payload.get('body', {}).get('data', '')
                    body_html = base64.urlsafe_b64decode(body_data).decode('utf-8')

                if body_html:
                    email_articles = parse_email_content(body_html)
                    articles.extend(email_articles)
                    print(f"Extracted {len(email_articles)} articles from: {subject}")

        except Exception as e:
            print(f"Error fetching from label {label_name}: {e}")

    return articles

def fetch_rss_feeds(feed_urls):
    """Fetch articles from RSS feeds"""
    articles = []
    print("Fetching RSS feeds...")

    for url in feed_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "snippet": entry.get('summary', '')[:200],
                    "source": "rss"
                })
        except Exception as e:
            print(f"Failed to parse {url}: {e}")

    return articles

def fetch_news():
    """Ingests news from RSS feeds and email newsletters"""
    articles = []

    # Aggregate feeds and labels from all shows
    all_feeds = set()
    all_labels = set()

    for show_key, config in SHOWS.items():
        # Collect feeds for this show
        feeds = config.get('feeds', [])
        all_feeds.update(feeds)

        # Collect Gmail labels for this show
        labels = config.get('gmail_labels', [])
        all_labels.update(labels)

    # Fetch from RSS feeds (deduplicated across shows)
    if all_feeds:
        print(f"Fetching from {len(all_feeds)} unique RSS feeds...")
        articles.extend(fetch_rss_feeds(list(all_feeds)))

    # Fetch from Gmail labels (deduplicated across shows)
    if all_labels:
        print(f"Fetching from {len(all_labels)} Gmail labels...")
        articles.extend(fetch_emails(list(all_labels)))

    print(f"Total articles fetched: {len(articles)}")
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

def select_articles(articles):
    """First pass: Claude selects the most interesting articles for each show"""

    # Build dynamic show descriptions from config
    show_list = []
    for key, config in SHOWS.items():
        keywords = ", ".join(config.get('keywords', []))
        show_list.append(f"- '{config['title']}' (key: {key}, Focus: {keywords})")

    shows_description = "\n    ".join(show_list)

    selection_prompt = f"""You are the Executive Producer of a media network. You run the following daily shows:
    {shows_description}

    Your Task:
    1. Analyze the provided news headlines and snippets.
    2. For EACH show, select up to 20 of the most relevant and interesting article URLs.
    3. Return ONLY the URLs that are worth covering, grouped by show.

    Return JSON format with keys matching the show keys (e.g., "stablecoin", "ai").
    Each value should be an array of URLs (strings) for that show.
    Example: {{"stablecoin": ["url1", "url2", ...], "ai": ["url3", "url4", ...]}}
    Do not include any text before or after the JSON object."""

    print("Step 1: Selecting top articles...")
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
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
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        else:
            print(f"ERROR: Could not parse selection response")
            return {}

def generate_scripts(selected_urls):
    """Second pass: Generate podcast scripts from full article content"""

    # Fetch full content for selected articles
    print("Step 2: Fetching full article content...")
    articles_by_show = {}

    for show_key, urls in selected_urls.items():
        articles_by_show[show_key] = []
        config = SHOWS.get(show_key, {})
        print(f"  {config.get('title', show_key)}: Fetching {len(urls)} articles...")

        for url in urls[:20]:  # Limit to 20 articles max
            content = fetch_article_content(url)
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
       - Tone: Insider, fast-paced, professional - like Bloomberg Radio or WSJ podcasts.
       - Each topic must include:
         * The key facts and what happened
         * Why it matters and the implications
         * Relevant context, numbers, or quotes from the article
         * Market impact, trends, or industry significance
       - NO generic statements like "In conclusion" or "This is important"
       - NO brief 1-2 sentence summaries - each topic needs FULL 30-second treatment
       - Example length: "PayPal just acquired Cymbio for an undisclosed sum to boost its agentic commerce capabilities. Cymbio's marketplace automation platform enables merchants to sell through AI-powered platforms like Microsoft Copilot and Perplexity. This acquisition comes as PayPal pushes deeper into AI-driven commerce, where conversational AI assistants are becoming new storefronts. The deal gives PayPal direct access to Cymbio's automated product feed management across 500+ marketplaces, positioning them ahead of traditional payment processors in the emerging agentic commerce space."
    3. Aggregate all topic summaries into a single podcast script for each show.
       - Start with a brief welcome (1-2 sentences)
       - Use smooth transitions between topics: "Next up...", "Meanwhile...", "In other news...", "Turning to..."
       - Each show should have approximately 20 topics with 30 seconds each = ~10 minutes total
       - End with a brief sign-off (1 sentence)

    CRITICAL: Each topic must be 75-90 words. If you provide shorter summaries, the podcast will be too short.

    Return JSON format only with keys: {keys_description}
    Each value should be the complete podcast script for that show.
    Do not include any text before or after the JSON object."""

    print("Step 3: Generating podcast scripts...")
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
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

def generate_audio(script_text, voice_model):
    """Converts text to WAV using Piper TTS, then to MP3"""
    model_path = os.path.join(MODELS_PATH, f"{voice_model}.onnx")
    config_path = os.path.join(MODELS_PATH, f"{voice_model}.onnx.json")

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file:
        wav_path = wav_file.name

    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as mp3_file:
        mp3_path = mp3_file.name

    try:
        # Run Piper to generate WAV
        process = subprocess.run(
            [
                PIPER_PATH,
                "--model", model_path,
                "--config", config_path,
                "--output_file", wav_path
            ],
            input=script_text.encode('utf-8'),
            capture_output=True,
            check=True
        )
        print(f"Piper output: {process.stderr.decode()}")

        # Convert WAV to MP3 using ffmpeg
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", wav_path,
                "-codec:a", "libmp3lame",
                "-qscale:a", "2",
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
        # 1. Ingest
        news_data = fetch_news()

        # 2. Select top articles
        selected_urls = select_articles(news_data)

        # 3. Generate scripts from full content
        scripts_json = generate_scripts(selected_urls)

        results = {}

        # 4. Production Loop
        for show_key, config in SHOWS.items():
            script_key = f"{show_key}_script"

            if script_key in scripts_json:
                print(f"Generating audio for {config['title']}...")
                audio_data = generate_audio(scripts_json[script_key], config['voice'])

                public_url = upload_to_bucket(audio_data, show_key)
                results[show_key] = public_url
            else:
                print(f"No script generated for {show_key}")

        # 5. Cleanup old episodes (older than 30 days)
        print("Cleaning up episodes older than 30 days...")
        for show_key in SHOWS.keys():
            cleanup_old_episodes(show_key, days_to_keep=30)

        # 6. Update RSS feeds
        feed_urls = update_podcast_feeds()

        return jsonify({
            "status": "success",
            "podcasts": results,
            "feeds": feed_urls
        }), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
