# Use Python slim image for smaller size
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LD_LIBRARY_PATH=/app/piper

# Set working directory
WORKDIR /app

# Install system dependencies (ffmpeg for audio conversion)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Download and install Piper TTS binary (auto-detect architecture)
RUN mkdir -p /app/piper && \
    ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ]; then PIPER_ARCH="arm64"; \
    else PIPER_ARCH="amd64"; fi && \
    wget -q https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_${PIPER_ARCH}.tar.gz \
        -O /tmp/piper.tar.gz && \
    tar -xzf /tmp/piper.tar.gz -C /app/piper --strip-components=1 && \
    rm /tmp/piper.tar.gz && \
    chmod +x /app/piper/piper

# Download Piper voice models
RUN mkdir -p /app/piper/models && \
    # en_US-ryan-high (deep, authoritative male voice)
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx \
        -O /app/piper/models/en_US-ryan-high.onnx && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx.json \
        -O /app/piper/models/en_US-ryan-high.onnx.json && \
    # en_US-amy-medium (energetic female voice)
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx \
        -O /app/piper/models/en_US-amy-medium.onnx && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json \
        -O /app/piper/models/en_US-amy-medium.onnx.json

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port for Cloud Run
EXPOSE 8080

# Start the application
CMD python main.py
