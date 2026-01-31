#!/bin/bash
# Setup Piper TTS on macOS (Apple Silicon)

set -e

echo "🎙️  Setting up Piper TTS for macOS..."

# Check for Homebrew and ffmpeg
if ! command -v brew &> /dev/null; then
    echo "❌ Homebrew not found. Install from https://brew.sh"
    exit 1
fi

if ! command -v ffmpeg &> /dev/null; then
    echo "📦 Installing ffmpeg..."
    brew install ffmpeg
else
    echo "✅ ffmpeg already installed"
fi

# Create piper directory
PIPER_DIR="./piper"
mkdir -p "$PIPER_DIR/models"

# Download Piper for macOS ARM64
echo "📥 Downloading Piper TTS (macOS ARM64)..."
PIPER_VERSION="v1.2.0"
PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_arm64.tar.gz"

if [ ! -f "$PIPER_DIR/piper" ]; then
    curl -L "$PIPER_URL" -o /tmp/piper.tar.gz
    tar -xzf /tmp/piper.tar.gz -C "$PIPER_DIR" --strip-components=1
    rm /tmp/piper.tar.gz
    chmod +x "$PIPER_DIR/piper"
    echo "✅ Piper installed"
else
    echo "✅ Piper already installed"
fi

# Download voice models
echo "📥 Downloading voice models..."

# en_US-ryan-high (deep, authoritative male voice)
if [ ! -f "$PIPER_DIR/models/en_US-ryan-high.onnx" ]; then
    echo "  - Downloading en_US-ryan-high..."
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx" \
        -o "$PIPER_DIR/models/en_US-ryan-high.onnx"
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx.json" \
        -o "$PIPER_DIR/models/en_US-ryan-high.onnx.json"
    echo "    ✅ en_US-ryan-high downloaded"
else
    echo "  ✅ en_US-ryan-high already downloaded"
fi

# en_US-amy-medium (energetic female voice)
if [ ! -f "$PIPER_DIR/models/en_US-amy-medium.onnx" ]; then
    echo "  - Downloading en_US-amy-medium..."
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx" \
        -o "$PIPER_DIR/models/en_US-amy-medium.onnx"
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json" \
        -o "$PIPER_DIR/models/en_US-amy-medium.onnx.json"
    echo "    ✅ en_US-amy-medium downloaded"
else
    echo "  ✅ en_US-amy-medium already downloaded"
fi

echo ""
echo "✅ Piper TTS setup complete!"
echo ""
echo "Test it with:"
echo "  echo 'Hello world' | ./piper/piper --model ./piper/models/en_US-ryan-high.onnx --output_file test.wav"
echo "  afplay test.wav"
