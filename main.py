"""Lazy Podinator — Flask app and pipeline orchestration."""

import os
import sys
import traceback

from flask import Flask, jsonify

from config import SHOWS, load_article_history, save_article_history
from ingestion import fetch_news
from selection import select_articles, generate_scripts
from audio import generate_audio
from publishing import (
    upload_to_bucket, cleanup_old_episodes, update_podcast_feeds,
    existing_episode_url_today,
)
from notifications import send_failure_notification

app = Flask(__name__)


def run_pipeline():
    """Run the full daily podcast pipeline once.

    Shared by the Flask route (Cloud Run) and the CLI entry point (CI/cron).
    Returns a dict with 'podcasts' and 'feeds'; raises on failure.
    """
    # 0. Load article history for deduplication
    article_history = load_article_history()

    # 1. Ingest
    news_data = fetch_news(article_history=article_history)

    # 2. Select top articles
    selected_urls = select_articles(news_data)
    if not selected_urls:
        raise RuntimeError("Article selection returned empty — aborting pipeline")

    # 3. Generate scripts from full content
    scripts_json = generate_scripts(selected_urls, all_articles=news_data)

    results = {}

    # 4. Generate audio sequentially (TTS is memory-intensive).
    #    Skip shows already generated today so a re-run after a mid-pipeline
    #    failure only regenerates the missing show(s).
    for show_key, show_cfg in SHOWS.items():
        script_key = f"{show_key}_script"
        if script_key not in scripts_json:
            print(f"No script generated for {show_key}")
            continue
        existing_url = existing_episode_url_today(show_key)
        if existing_url:
            print(f"Skipping {show_cfg['title']} — today's episode already exists")
            results[show_key] = existing_url
            continue
        print(f"Generating audio for {show_cfg['title']}...")
        audio_data = generate_audio(
            scripts_json[script_key], show_cfg['voice'], show_key=show_key
        )
        results[show_key] = upload_to_bucket(audio_data, show_key)

    # 5. Cleanup old episodes (older than 30 days)
    print("Cleaning up episodes older than 30 days...")
    for show_key in SHOWS:
        cleanup_old_episodes(show_key, days_to_keep=30)

    # 6. Update RSS feeds
    feed_urls = update_podcast_feeds()

    # 7. Save article history after successful completion
    all_covered_urls = []
    for urls in selected_urls.values():
        all_covered_urls.extend(urls)
    save_article_history(article_history, all_covered_urls)

    return {"podcasts": results, "feeds": feed_urls}


def _notify_failure(error, error_details):
    """Log and email a pipeline failure (no-op if notifications are unconfigured)."""
    print(f"Error occurred: {error}")
    print(f"Full traceback:\n{error_details}")
    send_failure_notification(
        subject="[Lazy Podinator] Pipeline failed",
        body=(
            "The daily podcast pipeline failed with the following error:\n\n"
            f"{error}\n\n{error_details}"
        ),
    )


@app.route('/', methods=['GET', 'POST'])
def daily_podcast_entrypoint():
    """The Cloud Run Entry Point"""
    try:
        result = run_pipeline()
        return jsonify({"status": "success", **result}), 200
    except Exception as e:
        _notify_failure(e, traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500


def _run_cli():
    """Run the pipeline once from the CLI (GitHub Actions / cron).

    Exits non-zero on failure so the CI job is marked failed.
    """
    try:
        result = run_pipeline()
        print(f"✓ Pipeline complete: {result}")
    except Exception as e:
        _notify_failure(e, traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        _run_cli()
    else:
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
