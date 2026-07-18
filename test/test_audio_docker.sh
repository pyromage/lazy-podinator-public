#!/bin/bash
# Test audio generation in Docker using the REAL pipeline (test/test_audio.py
# -> audio.py), matching production. Uses the default TTS engine (Kokoro), whose
# model is baked into the image; set TTS_ENGINE=piper to test the fallback.

set -e

echo "🎙️  Testing audio generation with Docker (matches production)..."

# Find Docker binary
if command -v docker > /dev/null 2>&1; then
    DOCKER_CMD="docker"
elif [ -f "/Applications/Docker.app/Contents/Resources/bin/docker" ]; then
    DOCKER_CMD="/Applications/Docker.app/Contents/Resources/bin/docker"
else
    echo "❌ Docker not found. Please install Docker Desktop."
    exit 1
fi

if ! $DOCKER_CMD info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop."
    exit 1
fi

if [ ! -f "output/scripts.json" ]; then
    echo "❌ No scripts found in output/scripts.json"
    echo "   Run: python test/test_local.py first"
    exit 1
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "❌ ANTHROPIC_API_KEY not set (needed to import app config). Run: source .env"
    exit 1
fi

echo "🔨 Building Docker image..."
$DOCKER_CMD build -t lazy-podinator-test . --quiet
echo "✅ Docker image built"

# Run the real audio test inside the container. shows_config.json is mounted so
# the container uses your local show definitions; output/ is mounted for the MP3s.
echo "🎧 Generating audio via test/test_audio.py inside the container..."
$DOCKER_CMD run --rm \
    -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    -e TTS_ENGINE="${TTS_ENGINE:-kokoro}" \
    -v "$(pwd)/output:/app/output" \
    -v "$(pwd)/shows_config.json:/app/shows_config.json" \
    lazy-podinator-test \
    python test/test_audio.py

echo ""
echo "✅ Done! MP3s are in output/ — e.g. afplay output/stablecoin_podcast.mp3"
