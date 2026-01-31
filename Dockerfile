# Use Python slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (ffmpeg for audio conversion)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Download and install Piper TTS binary
RUN mkdir -p /app/piper && \
    wget -q https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz -O /tmp/piper.tar.gz && \
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
