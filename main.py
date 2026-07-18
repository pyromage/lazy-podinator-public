"""Lazy Podinator — Flask app and pipeline orchestration."""

import os
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

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


def _synthesize_show(show_key, script_text, voice):
    """Worker: synthesize one show's MP3 bytes. Runs in a child process, so it
    does only CPU-bound TTS (no network) — uploads happen back in the parent to
    keep GCS/network clients out of forked children."""
    return generate_audio(script_text, voice, show_key=show_key)


def _produce_episodes(scripts_json):
    """Generate and upload today's episodes for shows that need one.

    Shows already generated today are skipped (idempotent re-runs). The rest are
    synthesized concurrently — one child process each — so one show's TTS/upload
    failure is logged and skipped rather than sinking the others. Uploads run
    here in the parent as each synthesis completes.

    Returns ``{show_key: public_url}`` for every show that published.
    """
    results = {}
    to_generate = []
    for show_key, show_cfg in SHOWS.items():
        if f"{show_key}_script" not in scripts_json:
            print(f"No script generated for {show_key}")
            continue
        existing_url = existing_episode_url_today(show_key)
        if existing_url:
            print(f"Skipping {show_cfg['title']} — today's episode already exists")
            results[show_key] = existing_url
            continue
        to_generate.append(show_key)

    if not to_generate:
        return results

    print(f"Generating audio for {len(to_generate)} show(s) in parallel...")
    with ProcessPoolExecutor(max_workers=len(to_generate)) as executor:
        futures = {
            executor.submit(
                _synthesize_show, key,
                scripts_json[f"{key}_script"], SHOWS[key]['voice']
            ): key
            for key in to_generate
        }
        for future in as_completed(futures):
            show_key = futures[future]
            title = SHOWS[show_key]['title']
            try:
                audio_data = future.result()
                results[show_key] = upload_to_bucket(audio_data, show_key)
                print(f"✓ Published {title}")
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"✗ Failed to produce {title}: {e}")

    return results


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

    # 4. Generate + upload today's episodes in parallel, isolating per-show
    #    failures so one bad show doesn't sink the others.
    results = _produce_episodes(scripts_json)

    # 5. Cleanup old episodes (older than 30 days)
    print("Cleaning up episodes older than 30 days...")
    for show_key in SHOWS:
        cleanup_old_episodes(show_key, days_to_keep=30)

    # 6. Update RSS feeds (reflects whatever published successfully)
    feed_urls = update_podcast_feeds()

    # 7. Save history only for shows that actually published, so a retry can
    #    still cover the articles of any show that failed.
    all_covered_urls = []
    for show_key, urls in selected_urls.items():
        if show_key in results:
            all_covered_urls.extend(urls)
    save_article_history(article_history, all_covered_urls)

    # 8. Surface partial failures: any show Claude selected that didn't publish.
    #    Raising marks the CI run failed so the auto-retry re-runs; idempotency
    #    (step 4) skips the shows that already succeeded, retrying only the gaps.
    failed_shows = [k for k, urls in selected_urls.items() if urls and k not in results]
    if failed_shows:
        raise RuntimeError(
            "Pipeline finished with missing episodes for: "
            f"{', '.join(failed_shows)}. Published: {', '.join(results) or 'none'}"
        )

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
