"""Article selection and script generation using Claude AI."""

import json
import time
import anthropic

from config import anthropic_client, CLAUDE_MODEL, SHOWS
from ingestion import fetch_article_content


def call_claude_with_retry(max_retries=3, **kwargs):
    """Call Claude API with exponential backoff for transient errors.
    Billing errors are surfaced immediately without retrying."""
    from notifications import send_failure_notification

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
            wait = 2 ** attempt
            print(f"API error (attempt {attempt+1}/{max_retries+1}): {e}. Retrying in {wait}s...")
            time.sleep(wait)


def select_articles(articles):
    """First pass: Claude selects the most interesting articles for each show"""

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

    print("Step 2: Fetching full article content...")
    articles_by_show = {}

    for show_key, urls in selected_urls.items():
        articles_by_show[show_key] = []
        config = SHOWS.get(show_key, {})
        print(f"  {config.get('title', show_key)}: Fetching {len(urls)} articles...")

        for url in urls[:20]:
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

    response_text = response.content[0].text

    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        import re
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        else:
            print(f"ERROR: Could not find JSON in response: {response_text[:500]}")
            raise
