"""Lazy Podinator — Flask app and pipeline orchestration."""

from flask import Flask, jsonify

from config import SHOWS, load_article_history, save_article_history
from ingestion import fetch_news
from selection import select_articles, generate_scripts
from audio import generate_audio
from publishing import upload_to_bucket, cleanup_old_episodes, update_podcast_feeds
from notifications import send_failure_notification

app = Flask(__name__)


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

        # 4. Generate audio sequentially (TTS is memory-intensive)
        for show_key, config in SHOWS.items():
            script_key = f"{show_key}_script"
            if script_key not in scripts_json:
                print(f"No script generated for {show_key}")
                continue
            print(f"Generating audio for {config['title']}...")
            audio_data = generate_audio(
                scripts_json[script_key], config['voice'], show_key=show_key
            )
            public_url = upload_to_bucket(audio_data, show_key)
            results[show_key] = public_url

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
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
