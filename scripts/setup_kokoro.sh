#!/bin/bash
# Download Kokoro TTS model for local audio testing (the default engine).
# In production, the Dockerfile and GitHub Actions workflow download this
# automatically — this script is only for running the pipeline on your machine.

set -e

echo "🎙️  Setting up Kokoro TTS (default engine) for local use..."

# ffmpeg is required for MP3 conversion
if ! command -v ffmpeg &> /dev/null; then
    if command -v brew &> /dev/null; then
        echo "📦 Installing ffmpeg via Homebrew..."
        brew install ffmpeg
    else
        echo "❌ ffmpeg not found. Install it (e.g. 'apt-get install ffmpeg')."
        exit 1
    fi
else
    echo "✅ ffmpeg already installed"
fi

# Python deps (kokoro-onnx, soundfile) ship in requirements.txt
echo "📦 Ensuring Python deps (kokoro-onnx, soundfile)..."
pip install -q kokoro-onnx soundfile

# Download the int8 model + voices (CPU-optimized, ~115MB total)
KOKORO_DIR="./kokoro"
mkdir -p "$KOKORO_DIR"
BASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"

if [ ! -f "$KOKORO_DIR/kokoro-v1.0.int8.onnx" ]; then
    echo "📥 Downloading Kokoro model (int8)..."
    curl -L "$BASE/kokoro-v1.0.int8.onnx" -o "$KOKORO_DIR/kokoro-v1.0.int8.onnx"
else
    echo "✅ Kokoro model already downloaded"
fi

if [ ! -f "$KOKORO_DIR/voices-v1.0.bin" ]; then
    echo "📥 Downloading Kokoro voices..."
    curl -L "$BASE/voices-v1.0.bin" -o "$KOKORO_DIR/voices-v1.0.bin"
else
    echo "✅ Kokoro voices already downloaded"
fi

echo ""
echo "✅ Kokoro TTS setup complete!"
echo ""
echo "Export these before running the pipeline locally:"
echo "  export TTS_ENGINE=kokoro"
echo "  export KOKORO_MODEL_PATH=$KOKORO_DIR/kokoro-v1.0.int8.onnx"
echo "  export KOKORO_VOICES_PATH=$KOKORO_DIR/voices-v1.0.bin"
