#!/usr/bin/env python3
"""
Local test: news fetching + article selection + script generation, using the
REAL pipeline (ingestion.py + selection.py) — no duplicated logic, so this
exercises the same code path as production. Audio is handled separately by
test/test_audio.py, which reads the output/scripts.json this writes.

Run from project root:

    source .env            # provides ANTHROPIC_API_KEY
    python test/test_local.py

Runs entirely offline of GCS: BUCKET_NAME is forced to "local-testing" so
shows_config.json is read from the local file and nothing is uploaded.
"""

import os
import sys
import json

# Make the app modules importable when run as `python test/test_local.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force local, GCS-free config loading BEFORE importing config (which reads
# BUCKET_NAME at import time). This keeps local runs deterministic and offline.
os.environ["BUCKET_NAME"] = "local-testing"

if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERROR: ANTHROPIC_API_KEY not set. Run: source .env")
    sys.exit(1)

# ruff: noqa: E402  (imports follow the sys.path/env setup above)
from config import SHOWS
from ingestion import fetch_news
from selection import select_articles, generate_scripts

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output"
)


def main():
    print("=" * 60)
    print("🎙️  LAZY PODINATOR - Local Test (real pipeline)")
    print("=" * 60)

    # 1. Ingest (real ingestion.fetch_news — pulls every show's feeds)
    articles = fetch_news()
    print(f"\n📰 Total articles fetched: {len(articles)}")
    if not articles:
        print("ERROR: No articles fetched. Check network / RSS feed URLs.")
        sys.exit(1)
    print("\n📋 Sample articles:")
    for i, article in enumerate(articles[:5]):
        print(f"  {i+1}. {article['title'][:60]}...")

    # 2. Select (real selection.select_articles — robust parse + retry)
    print("\n" + "-" * 60)
    selected_urls = select_articles(articles)
    if not selected_urls:
        print("ERROR: Article selection returned empty.")
        sys.exit(1)
    print("\n📊 Articles selected:")
    for show_key, urls in selected_urls.items():
        title = SHOWS.get(show_key, {}).get("title", show_key)
        print(f"  {title}: {len(urls)} articles")

    # 3. Generate scripts (real selection.generate_scripts — one call per show)
    scripts = generate_scripts(selected_urls, all_articles=articles)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    json_path = os.path.join(OUTPUT_DIR, "scripts.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(scripts, f, indent=2)
    print(f"\n💾 Saved scripts to: {json_path}")

    # 4. Summarize per-show results
    print("\n" + "=" * 60)
    print("📝 GENERATED SCRIPTS")
    print("=" * 60)
    for show_key, config in SHOWS.items():
        script_key = f"{show_key}_script"
        if script_key not in scripts:
            print(f"\n❌ No script generated for {config['title']}")
            continue
        script = scripts[script_key]
        word_count = len(script.split())
        script_path = os.path.join(OUTPUT_DIR, f"{show_key}_script.txt")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)
        print(f"\n🎧 {config['title']}")
        print(f"   Words: {word_count} | Est. duration: {word_count / 150:.1f} min")
        print(f"   💾 Saved to: {script_path}")
        print("-" * 60)
        print(script[:600])
        if len(script) > 600:
            print(f"\n... [{len(script) - 600} more characters]")

    generated = sum(1 for k in SHOWS if f"{k}_script" in scripts)
    print(f"\n✅ Test complete! {generated}/{len(SHOWS)} shows produced a script.")
    print("\nNext: generate audio locally with")
    print("  python test/test_audio.py")


if __name__ == "__main__":
    main()
