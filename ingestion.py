"""Content ingestion: RSS feeds, LinkedIn, and Gmail newsletters."""

import json
from datetime import datetime, timedelta
import feedparser
import requests
from bs4 import BeautifulSoup

from config import SHOWS, GMAIL_ENABLED


def fetch_linkedin_top_content(urls):
    """Fetch posts from LinkedIn top-content pages via JSON-LD structured data"""
    articles = []
    print("Fetching LinkedIn top-content pages...")

    for url in urls:
        try:
            response = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            soup = BeautifulSoup(response.content, 'html.parser')

            script_tags = soup.find_all('script', {'type': 'application/ld+json'})
            post_count = 0

            for script in script_tags:
                try:
                    data = json.loads(script.string)
                    items = []
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict) and data.get('@type') == 'ItemList':
                        items = data.get('itemListElement', [])
                    elif isinstance(data, dict) and data.get('@type') == 'Article':
                        items = [data]

                    for item in items:
                        article_data = item.get('item', item) if isinstance(item, dict) else item
                        if not isinstance(article_data, dict):
                            continue

                        title = article_data.get('headline', article_data.get('name', ''))
                        body = article_data.get('articleBody', '')
                        link = article_data.get('url', url)

                        if title:
                            snippet = normalize_for_tts(body[:200]) if body else title
                            articles.append({
                                "title": normalize_for_tts(title),
                                "snippet": snippet,
                                "link": link,
                                "source": "linkedin"
                            })
                            post_count += 1
                except (json.JSONDecodeError, AttributeError):
                    continue

            print(f"  {url}: {post_count} posts")
        except Exception as e:
            print(f"Failed to fetch LinkedIn top-content {url}: {e}")

    return articles


def normalize_for_tts(text):
    """Normalize Unicode text for TTS: convert fancy Unicode letters to ASCII, strip emojis/symbols."""
    import re
    import unicodedata

    text = text.encode('utf-8', errors='ignore').decode('utf-8')
    text = unicodedata.normalize('NFKD', text)

    result = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat[0] in ('L', 'N', 'P', 'Z') or ch in ('\n', '\t'):
            result.append(ch)
        else:
            result.append(' ')

    text = ''.join(result)
    text = re.sub(r'  +', ' ', text).strip()
    return text


def fetch_gmail_content(label_names):
    """Fetch newsletter content from Gmail messages with specified labels (last 24 hours)."""
    import base64
    from notifications import get_gmail_service

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
            while response.get('nextPageToken'):
                response = service.users().messages().list(
                    userId='me', labelIds=[label_id], q='newer_than:1d',
                    pageToken=response['nextPageToken']
                ).execute()
                for msg in response.get('messages', []):
                    msg_ids.add(msg['id'])
        except Exception as e:
            print(f"  WARNING: Could not list messages for label {label_id}: {e}")

    print(f"  Found {len(msg_ids)} emails from last 24 hours")

    for msg_id in msg_ids:
        try:
            msg = service.users().messages().get(
                userId='me', id=msg_id, format='full'
            ).execute()

            headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
            subject = headers.get('Subject', '(no subject)')

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


def fetch_article_content(url):
    """Fetch full article content from URL"""
    try:
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        soup = BeautifulSoup(response.content, 'html.parser')

        for script in soup(["script", "style", "nav", "footer", "aside"]):
            script.decompose()

        article_content = None
        for selector in ['article', '.article-content', '.post-content', 'main', '.entry-content']:
            article_content = soup.select_one(selector)
            if article_content:
                break

        if article_content:
            text = article_content.get_text(separator='\n', strip=True)
        else:
            text = soup.get_text(separator='\n', strip=True)

        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n'.join(lines)
        return text[:3000] if text else ""

    except Exception as e:
        print(f"Failed to fetch article {url}: {e}")
        return ""


def fetch_news(article_history=None):
    """Ingests news from all sources, with optional deduplication against history"""
    articles = []

    all_feeds = set()
    all_linkedin = set()

    for config in SHOWS.values():
        all_feeds.update(config.get('feeds', []))
        all_linkedin.update(config.get('linkedin_top_content', []))

    if all_feeds:
        print(f"Fetching from {len(all_feeds)} unique RSS feeds...")
        articles.extend(fetch_rss_feeds(list(all_feeds)))

    if all_linkedin:
        print(f"Fetching from {len(all_linkedin)} LinkedIn top-content pages...")
        articles.extend(fetch_linkedin_top_content(list(all_linkedin)))

    if GMAIL_ENABLED:
        all_gmail_labels = set()
        for config in SHOWS.values():
            all_gmail_labels.update(config.get('gmail_labels', []))
        if all_gmail_labels:
            print(f"Fetching from {len(all_gmail_labels)} Gmail labels...")
            articles.extend(fetch_gmail_content(list(all_gmail_labels)))

    print(f"Total articles fetched: {len(articles)}")

    if article_history and article_history.get("covered_urls"):
        covered = article_history["covered_urls"]
        before_count = len(articles)
        articles = [a for a in articles if a.get("link") not in covered]
        filtered_count = before_count - len(articles)
        if filtered_count > 0:
            print(f"Filtered out {filtered_count} previously covered articles")
        print(f"Total articles after filtering: {len(articles)}")

    return articles
