#!/usr/bin/env python3
"""
Test audio generation locally using Piper TTS.
Run from project root: python test/test_audio.py

Requires:
- Piper TTS installed locally (run scripts/setup_piper_macos.sh first)
- Output scripts from test_local.py
"""

import os
import json
import subprocess

# Load configs
def load_json_config(filename):
    # Look in parent directory (root of project)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    config_path = os.path.join(parent_dir, filename)
    with open(config_path, 'r') as f:
        return json.load(f)

SHOWS = load_json_config('shows_config.json')

# Piper configuration (local paths)
PIPER_PATH = "./piper/piper"
MODELS_PATH = "./piper/models"
OUTPUT_DIR = "./output"

def generate_audio(script_text, voice_model, output_filename):
    """Converts text to WAV using Piper TTS, then to MP3"""
    model_path = os.path.join(MODELS_PATH, f"{voice_model}.onnx")
    config_path = os.path.join(MODELS_PATH, f"{voice_model}.onnx.json")

    wav_path = os.path.join(OUTPUT_DIR, f"{output_filename}.wav")
    mp3_path = os.path.join(OUTPUT_DIR, f"{output_filename}.mp3")

    try:
        print(f"  🎙️  Generating audio with {voice_model}...")

        # Run Piper to generate WAV
        process = subprocess.run(
            [
                PIPER_PATH,
                "--model", model_path,
                "--config", config_path,
                "--output_file", wav_path
            ],
            input=script_text.encode('utf-8'),
            capture_output=True,
            check=True
        )

        print(f"  ✅ WAV generated: {wav_path}")

        # Convert WAV to MP3 using ffmpeg
        print(f"  🔄 Converting to MP3...")
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", wav_path,
                "-codec:a", "libmp3lame",
                "-qscale:a", "2",
                mp3_path
            ],
            capture_output=True,
            check=True
        )

        print(f"  ✅ MP3 generated: {mp3_path}")

        # Get file size
        mp3_size = os.path.getsize(mp3_path)
        print(f"     Size: {mp3_size / 1024 / 1024:.2f} MB")

        return mp3_path

    except subprocess.CalledProcessError as e:
        print(f"  ❌ Error: {e.stderr.decode() if e.stderr else str(e)}")
        return None
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None

def main():
    print("=" * 60)
    print("🎙️  LAZY PODINATOR - Audio Test")
    print("=" * 60)

    # Check if Piper is installed
    if not os.path.exists(PIPER_PATH):
        print("\n❌ Piper not found!")
        print("Run setup script first:")
        print("  chmod +x scripts/setup_piper_macos.sh")
        print("  ./scripts/setup_piper_macos.sh")
        exit(1)

    # Check if output directory exists
    if not os.path.exists(OUTPUT_DIR):
        print(f"\n❌ Output directory not found: {OUTPUT_DIR}")
        print("Run test_local.py first to generate scripts")
        exit(1)

    # Load scripts from JSON
    scripts_path = os.path.join(OUTPUT_DIR, 'scripts.json')
    if not os.path.exists(scripts_path):
        print(f"\n❌ Scripts not found: {scripts_path}")
        print("Run test_local.py first to generate scripts")
        exit(1)

    with open(scripts_path, 'r') as f:
        scripts = json.load(f)

    print(f"\n🎧 Generating audio for {len(SHOWS)} shows...\n")

    for show_key, config in SHOWS.items():
        script_key = f"{show_key}_script"

        if script_key not in scripts:
            print(f"⚠️  No script found for {config['title']}")
            continue

        print(f"📻 {config['title']}")
        script = scripts[script_key]
        word_count = len(script.split())
        est_duration = word_count / 150
        print(f"   Words: {word_count} | Est. duration: {est_duration:.1f} minutes")

        output_filename = f"{show_key}_podcast"
        mp3_path = generate_audio(script, config['voice'], output_filename)

        if mp3_path:
            print(f"\n   🎵 Play with: afplay {mp3_path}")

        print()

    print("=" * 60)
    print("✅ Audio generation complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
