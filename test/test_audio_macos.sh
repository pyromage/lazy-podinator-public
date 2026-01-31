#!/bin/bash
# Quick audio test using macOS built-in 'say' command
# Note: This won't match Piper TTS voices, but good for quick testing

set -e

echo "🎙️  Testing audio with macOS 'say' command..."

# Check if output/scripts.json exists
if [ ! -f "output/scripts.json" ]; then
    echo "❌ No scripts found in output/scripts.json"
    echo "Run: python test/test_local.py first"
    exit 1
fi

echo ""
echo "Available macOS voices:"
echo "  - Alex (default male)"
echo "  - Samantha (female)"
echo "  - Daniel (British male)"
echo ""

# Generate audio for stablecoin script
if [ -f "output/stablecoin_script.txt" ]; then
    echo "📻 The Stablecoin Ledger (using Alex voice)..."
    say -v Alex -f output/stablecoin_script.txt -o output/stablecoin_test.aiff
    # Convert to MP3
    ffmpeg -y -loglevel error -i output/stablecoin_test.aiff -codec:a libmp3lame -qscale:a 2 output/stablecoin_test.mp3
    rm output/stablecoin_test.aiff
    SIZE=$(du -h output/stablecoin_test.mp3 | cut -f1)
    echo "  ✅ Generated: output/stablecoin_test.mp3 ($SIZE)"
fi

# Generate audio for AI script
if [ -f "output/ai_script.txt" ]; then
    echo "📻 AI Morning Brief (using Samantha voice)..."
    say -v Samantha -f output/ai_script.txt -o output/ai_test.aiff
    # Convert to MP3
    ffmpeg -y -loglevel error -i output/ai_test.aiff -codec:a libmp3lame -qscale:a 2 output/ai_test.mp3
    rm output/ai_test.aiff
    SIZE=$(du -h output/ai_test.mp3 | cut -f1)
    echo "  ✅ Generated: output/ai_test.mp3 ($SIZE)"
fi

echo ""
echo "✅ Done!"
echo ""
echo "Play with:"
echo "  afplay output/stablecoin_test.mp3"
echo "  afplay output/ai_test.mp3"
echo ""
echo "Note: These use macOS voices, not Piper TTS."
echo "      For production-quality audio, use Docker: ./test/test_audio_docker.sh"
