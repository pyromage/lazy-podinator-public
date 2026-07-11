# Claude Code Instructions

## Pre-commit Quality Checks

Before any commit, run the following tools and fix all issues:

```bash
# 1. Lint — fix all errors
ruff check --fix .

# 2. Security scan — fix any Medium or High severity issues
bandit -r main.py scripts/ test/ -ll

# 3. Code quality — target 9.0+ score, fix warnings
pylint main.py scripts/setup_gmail.py --disable=C0114,C0115,C0116

# 4. Markdown lint — fix all errors (ignore line-length)
markdownlint README.md SETUP.md CLAUDE.md artwork/README.md --disable MD013

# 5. Run tests — must pass before committing
source .env && python test/test_local.py
```

Test scripts call the Anthropic API so they require `ANTHROPIC_API_KEY`.
The test generates output in `output/` — review the scripts for quality.

### Accepted pylint suppressions

Do not fix these:

- `broad-exception-caught` — intentional in pipeline error handling
- `import-outside-toplevel` — optional/conditional imports
- `line-too-long` — allowed in prompt strings and URLs only
- `no-member` on `googleapiclient.discovery.build` — false positive

## Public Repo Rules

This is a public repo meant for others to fork and use. Follow these rules:

- Never hardcode secrets, API keys, passwords, or credentials in code
- Never hardcode project-specific config (project IDs, bucket names,
  email addresses, RSS feeds) in code
- All secrets and config values must come from `.env` or environment variables
- New config parameters get a generic placeholder in `.env.example`
- Personal config files (`.env`, `shows_config.json`, credential JSONs)
  must be in `.gitignore`
- Provide `.example` templates for any gitignored config file
- Before committing, scan tracked files for leaked secrets or personal data

## Project Structure

- `main.py` — Flask app + `run_pipeline()` orchestration (`python main.py run` for CI/cron)
- `config.py` — shared config, clients, GCS config/history helpers
- `ingestion.py` — RSS + newsletter fetching
- `selection.py` — Claude article selection and script generation
- `audio.py` — TTS (Kokoro default, Piper fallback), pronunciation fixes, MP3 conversion
- `publishing.py` — GCS upload, episode cleanup, RSS feed generation
- `notifications.py` — Gmail failure notifications
- `.github/workflows/` — daily pipeline (GitHub Actions) + auto-retry on failure
- `scripts/` — deployment and setup scripts
- `test/` — testing scripts (not pytest, run directly)
- `shows_config.json` — personal config (gitignored)
- `shows_config.example.json` — public template

## Environment

- Python 3.11+
- Runs daily via GitHub Actions (free public-repo runners); Cloud Run (Docker) optional
- Publishes to Google Cloud Storage; `shows_config.json` loaded from GCS at runtime
- GCP project: uses `PROJECT_ID` from `.env`
- All secrets in `.env` (gitignored) — never hardcode credentials

## Key Patterns

- Anthropic API calls go through `call_claude_with_retry()`
- Never call `anthropic_client.messages.create()` directly
- Model name comes from `CLAUDE_MODEL` env var
- Gmail OAuth token stored in GCS at `config/gmail_token.json`
- `send_failure_notification()` is called from error paths
- It silently skips if not configured
