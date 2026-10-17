# Lazy Podinator

Automation engine that turns news feeds into daily AI-hosted podcasts. Every morning it ingests headlines, uses Claude to select and script the top stories, generates audio with Kokoro TTS, and publishes a podcast-ready RSS feed. Runs free on GitHub Actions.

## How It Works

1. **Ingests** headlines from RSS feeds, LinkedIn top-content pages, and (optionally) Gmail newsletters
2. **Selects** up to 20 relevant, unique stories per show using Claude, skipping articles covered in the last 30 days
3. **Fetches** full article text, discarding block pages, 403s, and redirect stubs (falls back to the RSS summary)
4. **Scripts** each show in its own Claude call, sized to the show's `duration` (~185 words per minute)
5. **Generates** audio for all shows in parallel using Kokoro TTS (free, open-source; Piper available as a fallback)
6. **Publishes** MP3 + RSS feed to Google Cloud Storage, and removes episodes older than 30 days
7. **Delivers** via Spotify, Apple Podcasts, or any podcast app

## Stack

- **Compute:** GitHub Actions (free unlimited minutes on public repos) — Cloud Run (Docker) optional
- **Trigger:** Scheduled GitHub Actions workflow (daily cron) — Cloud Scheduler optional
- **Storage:** Google Cloud Storage
- **AI:** Anthropic Claude API — model set via `CLAUDE_MODEL`, with `CLAUDE_FALLBACK_MODEL` used on refusals
- **TTS:** Kokoro TTS by default, Piper as fallback (both bundled in container, set via `TTS_ENGINE`)
- **Notifications:** GitHub issue assigned to the repo owner on repeated failure; Gmail API alerts optional

## Reliability

- **Structured outputs** — Claude responses use a JSON schema, with a parse-and-retry fallback
- **Per-show isolation** — one show failing does not block the others; successful shows still publish
- **Auto-retry** — `retry.yml` re-runs a failed daily run once; the pipeline is idempotent, so a retry only fills the gaps
- **Keepalive** — the daily workflow re-enables itself so GitHub does not disable the schedule after 60 days without commits
- **Billing errors** fail fast instead of retrying

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
- The Final Frontier Daily (space exploration)

## Cost

Runs for free on GitHub Actions (unlimited minutes for public repos), with GCS storage within the free tier. The only recurring cost is Anthropic API usage, ~$0.50-$2.00/month depending on number of shows.

## License

MIT
