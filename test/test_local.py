#!/usr/bin/env python3
"""
Local test script - tests news fetching and script generation without audio.
Run from project root: python test/test_local.py

Requires:
- ANTHROPIC_API_KEY environment variable set
- pip install feedparser anthropic beautifulsoup4
"""

import os
import json
import feedparser
import anthropic
import requests
from bs4 import BeautifulSoup

# Check for API key
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("ERROR: Set ANTHROPIC_API_KEY environment variable")
    print("  export ANTHROPIC_API_KEY='your-key-here'")
    exit(1)

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

# Initialize Anthropic client
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Load configs
def load_json_config(filename):
    # Look in parent directory (root of project)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    config_path = os.path.join(parent_dir, filename)
    with open(config_path, 'r') as f:
        return json.load(f)

SHOWS = load_json_config('shows_config.json')

def fetch_rss_feeds(feed_urls):
    """Fetch articles from RSS feeds, filtering to last 7 days"""
    from datetime import datetime, timedelta
    from time import mktime
    articles = []
    cutoff_date = datetime.now() - timedelta(days=7)
    print("\n📡 Fetching RSS feeds...")

    for url in feed_urls:
        try:
            print(f"  - {url}")
            feed = feedparser.parse(url)
            count = 0
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
                count += 1
            print(f"    ✓ {count} articles")
        except Exception as e:
            print(f"    ✗ Error: {e}")

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
        print(f"    ✗ Error fetching {url}: {e}")
        return ""

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

    print("\n🔍 Step 1: Selecting top articles...")
    response = client.messages.create(
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
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        else:
            print("ERROR: Could not parse selection response")
            return {}

def generate_scripts(selected_urls):
    """Second pass: Generate podcast scripts from full article content"""

    # Fetch full content for selected articles
    print("\n📰 Step 2: Fetching full article content...")
    articles_by_show = {}

    for show_key, urls in selected_urls.items():
        articles_by_show[show_key] = []
        print(f"\n  {SHOWS[show_key]['title']}: Fetching {len(urls)} articles...")

        for url in urls[:20]:  # Limit to 20 articles max
            content = fetch_article_content(url)
            if content:
                articles_by_show[show_key].append({
                    "url": url,
                    "content": content
                })
                print(f"    ✓ {url[:60]}...")

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

    PRONUNCIATION FOR TEXT-TO-SPEECH:
    These scripts will be read aloud by a text-to-speech engine. To ensure correct pronunciation:
    - Spell out acronyms with periods between letters: USDC -> "U.S.D.C.", CBDC -> "C.B.D.C.", LLM -> "L.L.M.", ESA -> "E.S.A.", FSDP -> "F.S.D.P."
    - Exception for acronyms commonly pronounced as words: NASA, JAXA, ISRO stay as-is
    - Write "xAI" as "ex A.I." and "GenAI" as "Jen A.I."
    - Avoid leaving bare acronyms that a TTS engine might try to pronounce as a single word

    Return JSON format only with keys: {keys_description}
    Each value should be the complete podcast script for that show.
    Do not include any text before or after the JSON object."""

    print("\n🤖 Step 3: Generating podcast scripts...")
    response = client.messages.create(
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

def main():
    print("=" * 60)
    print("🎙️  LAZY PODINATOR - Local Test")
    print("=" * 60)

    # Step 1: Fetch news from all shows
    all_feeds = set()
    for show_key, config in SHOWS.items():
        feeds = config.get('feeds', [])
        all_feeds.update(feeds)

    print(f"\n🔍 Fetching from {len(all_feeds)} unique RSS feeds...")
    articles = fetch_rss_feeds(list(all_feeds))

    print(f"\n📰 Total articles fetched: {len(articles)}")

    if len(articles) == 0:
        print("ERROR: No articles fetched. Check your RSS feed URLs.")
        exit(1)

    # Show sample articles
    print("\n📋 Sample articles:")
    for i, article in enumerate(articles[:5]):
        print(f"  {i+1}. {article['title'][:60]}...")

    # Step 2: Select articles
    print("\n" + "-" * 60)
    selected_urls = select_articles(articles)

    print("\n📊 Articles selected:")
    for show_key, urls in selected_urls.items():
        show_title = SHOWS.get(show_key, {}).get('title', show_key)
        print(f"  {show_title}: {len(urls)} articles")

    # Step 3: Generate scripts from full content
    scripts = generate_scripts(selected_urls)

    # Save scripts to files (in root directory)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    output_dir = os.path.join(parent_dir, 'output')
    os.makedirs(output_dir, exist_ok=True)

    # Save full JSON
    json_path = os.path.join(output_dir, 'scripts.json')
    with open(json_path, 'w') as f:
        json.dump(scripts, f, indent=2)
    print(f"\n💾 Saved full JSON to: {json_path}")

    # Step 3: Display results and save individual scripts
    print("\n" + "=" * 60)
    print("📝 GENERATED SCRIPTS")
    print("=" * 60)

    for show_key, config in SHOWS.items():
        script_key = f"{show_key}_script"
        if script_key in scripts:
            script = scripts[script_key]
            word_count = len(script.split())
            # Estimate duration: ~150 words per minute for speech
            est_duration = word_count / 150

            # Save individual script to text file
            script_path = os.path.join(output_dir, f'{show_key}_script.txt')
            with open(script_path, 'w') as f:
                f.write(script)

            print(f"\n🎧 {config['title']}")
            print(f"   Words: {word_count} | Est. duration: {est_duration:.1f} minutes")
            print(f"   💾 Saved to: {script_path}")
            print("-" * 60)
            print(script[:1000])
            if len(script) > 1000:
                print(f"\n... [{len(script) - 1000} more characters]")
            print("-" * 60)
        else:
            print(f"\n❌ No script generated for {config['title']}")

    print("\n✅ Test complete!")
    print("\nNext steps:")
    print("  1. If scripts look good, test with Docker:")
    print("     docker build -t lazy-podinator .")
    print("     docker run -p 8080:8080 -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY -e BUCKET_NAME=test lazy-podinator")
    print("  2. Then trigger: curl http://localhost:8080")

if __name__ == "__main__":
    main()
