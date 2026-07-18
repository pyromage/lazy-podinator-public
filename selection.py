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


def _parse_json_response(response_text):
    """Extract a JSON object from a Claude response, tolerating code fences and
    surrounding prose. Raises ValueError if no valid JSON object can be found."""
    import re

    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    cleaned = re.sub(r'^```(?:json)?\s*', '', response_text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed JSON in response: {e}") from e

    raise ValueError("No JSON object found in response")


def _call_and_parse_json(max_parse_retries=2, **kwargs):
    """Call Claude and parse a JSON object from the reply, re-calling on parse
    failure. call_claude_with_retry covers transient API errors; this adds a
    retry for the non-deterministic case where the model returns malformed or
    truncated JSON (the top cause of pipeline failures)."""
    last_err = None
    for attempt in range(max_parse_retries + 1):
        response = call_claude_with_retry(**kwargs)
        text = response.content[0].text
        try:
            return _parse_json_response(text)
        except ValueError as e:
            last_err = e
            print(f"JSON parse failed (attempt {attempt+1}/{max_parse_retries+1}): {e}. "
                  f"Raw response head:\n{text[:300]}")
    raise ValueError(f"Could not parse JSON after {max_parse_retries+1} attempts: {last_err}")


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
    try:
        return _call_and_parse_json(
            model=CLAUDE_MODEL,
            max_tokens=8192,
            messages=[
                {
                    "role": "user",
                    "content": f"{selection_prompt}\n\nHeadlines:\n{json.dumps(articles)}"
                }
            ]
        )
    except ValueError as e:
        print(f"ERROR: Could not parse selection response after retries: {e}")
        return {}


def _fetch_articles_by_show(selected_urls, all_articles=None):
    """Fetch full article content for each show's selected URLs."""
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

    return articles_by_show


def _build_script_prompt(config):
    """Build the single-show script-writing prompt."""
    keywords = ", ".join(config.get('keywords', []))
    return f"""You are the host and producer of the daily show '{config['title']}' (Focus: {keywords}).

    Your Task:
    1. You have been provided with full article content for this show.
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
    3. Aggregate all topic summaries into a single podcast script.
       - Start with a natural welcome (1-2 sentences) - sound like a radio host, not a robot
       - After EACH topic, add a clear pause marker: "... [PAUSE] ..."
       - Use smooth transitions: "Next up...", "Meanwhile...", "In other news...", "Moving on...", "Here's an interesting one..."
       - The show should have approximately 20 topics with 30 seconds each = ~10 minutes total
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

    Return a JSON object with a single key "script" whose value is the complete podcast script.
    Do not include any text before or after the JSON object."""


def generate_scripts(selected_urls, all_articles=None):
    """Second pass: generate one podcast script per show.

    Each show is generated in its own Claude call so that a malformed/truncated
    response for one show only loses that show — not all of them — and so no
    single response has to fit every show's script within one token budget
    (the previous all-shows-in-one-call design was the main failure mode).

    Returns a dict of ``{"<show_key>_script": text}`` for the shows that
    succeeded; failed shows are simply omitted and skipped downstream.
    """
    articles_by_show = _fetch_articles_by_show(selected_urls, all_articles)

    print("Step 3: Generating podcast scripts (one call per show)...")
    scripts = {}
    for show_key, articles in articles_by_show.items():
        config = SHOWS.get(show_key, {})
        title = config.get('title', show_key)
        if not articles:
            print(f"  ✗ {title}: no article content — skipping")
            continue
        try:
            result = _call_and_parse_json(
                model=CLAUDE_MODEL,
                max_tokens=8192,
                messages=[
                    {
                        "role": "user",
                        "content": f"{_build_script_prompt(config)}\n\nArticles:\n{json.dumps(articles)}"
                    }
                ]
            )
            script_text = result.get("script") or result.get(f"{show_key}_script")
            if script_text:
                scripts[f"{show_key}_script"] = script_text
                print(f"  ✓ {title}: script generated ({len(script_text)} chars)")
            else:
                print(f"  ✗ {title}: response contained no 'script' field")
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"  ✗ {title}: script generation failed: {e}")

    if not scripts:
        raise RuntimeError("Script generation produced no scripts for any show")

    return scripts
