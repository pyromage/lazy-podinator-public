#!/bin/bash
# Test audio generation using Docker (which includes Piper TTS)

set -e

echo "🎙️  Testing audio generation with Docker..."

# Find Docker binary
if command -v docker > /dev/null 2>&1; then
    DOCKER_CMD="docker"
elif [ -f "/Applications/Docker.app/Contents/Resources/bin/docker" ]; then
    DOCKER_CMD="/Applications/Docker.app/Contents/Resources/bin/docker"
else
    echo "❌ Docker not found. Please install Docker Desktop."
    exit 1
fi

# Check if Docker is running
if ! $DOCKER_CMD info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Build Docker image if needed
echo "🔨 Building Docker image..."
$DOCKER_CMD build -t lazy-podinator-test . --quiet

# Check if output/scripts.json exists
if [ ! -f "output/scripts.json" ]; then
    echo "❌ No scripts found in output/scripts.json"
    echo "Run: python test/test_local.py first"
    exit 1
fi

echo "✅ Docker image built"
echo ""

# Create a temporary Python script that reads scripts.json and generates audio
cat > /tmp/generate_audio.py << 'EOF'
import os
import json
import subprocess
import sys

PIPER_PATH = "/app/piper/piper"
MODELS_PATH = "/app/piper/models"

def load_json_config(filename):
    with open(filename, 'r') as f:
        return json.load(f)

SHOWS = load_json_config('/app/shows_config.json')

def generate_audio(script_text, voice_model, output_filename):
    """Converts text to WAV using Piper TTS, then to MP3"""
    model_path = os.path.join(MODELS_PATH, f"{voice_model}.onnx")
    config_path = os.path.join(MODELS_PATH, f"{voice_model}.onnx.json")

    wav_path = f"/app/output/{output_filename}.wav"
    mp3_path = f"/app/output/{output_filename}.mp3"

    try:
        print(f"  🎙️  Generating audio with {voice_model}...")

        # Run Piper to generate WAV
        process = subprocess.run(
            [PIPER_PATH, "--model", model_path, "--config", config_path, "--output_file", wav_path],
            input=script_text.encode('utf-8'),
            capture_output=True,
            check=True
        )

        print(f"  ✅ WAV generated: {output_filename}.wav")

        # Convert WAV to MP3 using ffmpeg
        print(f"  🔄 Converting to MP3...")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", mp3_path],
            capture_output=True,
            check=True
        )

        print(f"  ✅ MP3 generated: {output_filename}.mp3")

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

# Load scripts
with open('/app/output/scripts.json', 'r') as f:
    scripts = json.load(f)

print("=" * 60)
print("🎙️  LAZY PODINATOR - Audio Generation")
print("=" * 60)
print()

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
    generate_audio(script, config['voice'], output_filename)
    print()

print("=" * 60)
print("✅ Audio generation complete!")
print("=" * 60)
print()
print("Generated files in output/:")
print("  - stablecoin_podcast.mp3")
print("  - ai_podcast.mp3")
print()
print("Play with: afplay output/stablecoin_podcast.mp3")
EOF

# Run the Docker container with the script
echo "🎧 Generating audio files..."
$DOCKER_CMD run --rm \
    -v "$(pwd)/output:/app/output" \
    -v "$(pwd)/shows_config.json:/app/shows_config.json" \
    -v "/tmp/generate_audio.py:/app/generate_audio.py" \
    lazy-podinator-test \
    python /app/generate_audio.py

echo ""
echo "✅ Done! Audio files are in the output/ directory"
echo ""
echo "Play them with:"
echo "  afplay output/stablecoin_podcast.mp3"
echo "  afplay output/ai_podcast.mp3"
