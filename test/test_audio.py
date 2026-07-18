#!/usr/bin/env python3
"""
Test audio generation locally using the REAL pipeline (audio.py).

Exercises the configured TTS engine (Kokoro by default, Piper fallback) via the
same code path as production — no duplicated audio logic. Run from project root:

    python test/test_audio.py

Requires:
- Scripts from a prior run: `python test/test_local.py` (writes output/scripts.json)
- ANTHROPIC_API_KEY set (needed to import the app config): `source .env`
- Kokoro model available: `./scripts/setup_kokoro.sh` then export
  KOKORO_MODEL_PATH / KOKORO_VOICES_PATH
  (or Piper installed for TTS_ENGINE=piper: `./scripts/setup_piper_macos.sh`)
"""

import os
import sys
import json

# Make the app modules importable when run as `python test/test_audio.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importing config initializes the Anthropic client, which needs a key present.
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERROR: ANTHROPIC_API_KEY not set (needed to import app config).")
    print("  Run: source .env")
    sys.exit(1)

# ruff: noqa: E402  (imports follow the sys.path/env setup above)
from config import SHOWS, TTS_ENGINE, KOKORO_MODEL_PATH, PIPER_PATH
from audio import generate_audio

OUTPUT_DIR = "output"


def preflight():
    """Fail early with a helpful message if the engine's model/binary is missing."""
    if TTS_ENGINE == "piper":
        if not os.path.exists(PIPER_PATH):
            print(f"❌ Piper not found at {PIPER_PATH}")
            print("   Run: ./scripts/setup_piper_macos.sh")
            sys.exit(1)
    elif not os.path.exists(KOKORO_MODEL_PATH):
        print(f"❌ Kokoro model not found at {KOKORO_MODEL_PATH}")
        print("   Run: ./scripts/setup_kokoro.sh")
        print("   then export KOKORO_MODEL_PATH and KOKORO_VOICES_PATH")
        sys.exit(1)


def main():
    print("=" * 60)
    print(f"🎙️  LAZY PODINATOR - Audio Test (engine: {TTS_ENGINE})")
    print("=" * 60)

    preflight()

    scripts_path = os.path.join(OUTPUT_DIR, "scripts.json")
    if not os.path.exists(scripts_path):
        print(f"\n❌ Scripts not found: {scripts_path}")
        print("   Run `python test/test_local.py` first to generate scripts")
        sys.exit(1)

    with open(scripts_path, "r", encoding="utf-8") as f:
        scripts = json.load(f)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\n🎧 Generating audio for {len(SHOWS)} shows...\n")

    for show_key, show_cfg in SHOWS.items():
        script_key = f"{show_key}_script"
        if script_key not in scripts:
            print(f"⚠️  No script found for {show_cfg['title']}")
            continue

        script = scripts[script_key]
        word_count = len(script.split())
        print(f"📻 {show_cfg['title']}")
        print(f"   Words: {word_count} | Est. duration: {word_count / 150:.1f} min")

        try:
            mp3 = generate_audio(script, show_cfg["voice"], show_key=show_key)
        except Exception as e:  # surface any engine error without aborting other shows
            print(f"   ❌ Error: {e}\n")
            continue

        out_path = os.path.join(OUTPUT_DIR, f"{show_key}_podcast.mp3")
        with open(out_path, "wb") as f:
            f.write(mp3)
        print(f"   ✅ {out_path} ({len(mp3) / 1024 / 1024:.2f} MB)")
        print(f"   🎵 Play: afplay {out_path}\n")

    print("=" * 60)
    print("✅ Audio generation complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
