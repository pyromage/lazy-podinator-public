# Lazy Podinator

Serverless automation engine that turns RSS feeds into daily AI-hosted podcasts. Every morning it ingests headlines, uses Claude to select and script the top stories, generates audio with Kokoro TTS, and publishes a podcast-ready RSS feed.

## How It Works

1. **Ingests** headlines from RSS feeds and LinkedIn top-content pages
2. **Selects** up to 20 relevant topics per show using Claude AI
3. **Scripts** a ~30-second discussion per topic (~10 min total)
4. **Generates** audio using Kokoro TTS (free, open-source; Piper available as a fallback)
5. **Publishes** MP3 + RSS feed to Google Cloud Storage
6. **Delivers** via Spotify, Apple Podcasts, or any podcast app

## Stack

- **Compute:** GitHub Actions (free unlimited minutes on public repos) — Cloud Run (Docker) optional
- **Trigger:** Scheduled GitHub Actions workflow (daily cron) — Cloud Scheduler optional
- **Storage:** Google Cloud Storage
- **AI:** Anthropic Claude API
- **TTS:** Kokoro TTS by default, Piper as fallback (both bundled in container, set via `TTS_ENGINE`)
- **Notifications:** Gmail API (failure alerts)

## Quick Start

See [SETUP.md](SETUP.md) for full setup and deployment instructions.

```bash
cp shows_config.example.json shows_config.json
cp .env.example .env
# Edit both files with your values, then:
source .env && python test/test_local.py
```

## Live Example Shows

- [AI Technology Morning Brief](https://open.spotify.com/show/6ltJZXfvr5ZeSavapFO056) on Spotify
- [The Stablecoin Ledger](https://open.spotify.com/show/5HxDtAnJk9FNCWVyQw8cmh) on Spotify

## Cost

Runs for free on GitHub Actions (unlimited minutes for public repos), with GCS storage within the free tier. The only recurring cost is Anthropic API usage, ~$0.50-$2.00/month depending on number of shows.

## License

MIT
