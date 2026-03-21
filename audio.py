"""Audio generation: TTS with Piper, pronunciation fixes, MP3 conversion."""

import os
import subprocess
import tempfile

from config import load_json_config, PIPER_PATH, MODELS_PATH


# Pronunciation guide cache
_pronunciation_guide = None


def load_pronunciation_guide():
    """Load pronunciation guide (cached after first load)"""
    global _pronunciation_guide
    if _pronunciation_guide is None:
        try:
            _pronunciation_guide = load_json_config('pronunciation_guide.json')
        except Exception as e:
            print(f"Warning: Could not load pronunciation guide: {e}")
            _pronunciation_guide = {"acronyms": {}, "proper_nouns": {}, "technical_terms": {}}
    return _pronunciation_guide


def apply_pronunciation_fixes(text, show_key=None):
    """Replace difficult words with TTS-friendly respellings before Piper TTS."""
    import re
    guide = load_pronunciation_guide()

    for category in ['acronyms', 'proper_nouns']:
        for word, respelling in guide.get(category, {}).items():
            pattern = r'\b' + re.escape(word) + r'\b'
            text = re.sub(pattern, respelling, text)

    for word, respelling in guide.get('technical_terms', {}).items():
        pattern = r'\b' + re.escape(word) + r'\b'
        text = re.sub(pattern, respelling, text, flags=re.IGNORECASE)

    return text


def generate_audio(script_text, voice_model, show_key=None):
    """Converts text to WAV using Piper TTS, then to MP3 with natural pacing"""
    model_path = os.path.join(MODELS_PATH, f"{voice_model}.onnx")
    config_path = os.path.join(MODELS_PATH, f"{voice_model}.onnx.json")

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file:
        wav_path = wav_file.name

    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as mp3_file:
        mp3_path = mp3_file.name

    try:
        cleaned_text = script_text.replace("[PAUSE]", "").replace("...", ".")
        cleaned_text = apply_pronunciation_fixes(cleaned_text, show_key=show_key)

        process = subprocess.run(
            [
                PIPER_PATH,
                "--model", model_path,
                "--config", config_path,
                "--length-scale", "1.1",
                "--sentence-silence", "0.8",
                "--output_file", wav_path
            ],
            input=cleaned_text.encode('utf-8'),
            capture_output=True,
            check=True
        )
        print(f"Piper output: {process.stderr.decode()}")

        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", wav_path,
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-codec:a", "libmp3lame",
                "-qscale:a", "2",
                mp3_path
            ],
            capture_output=True,
            check=True
        )

        with open(mp3_path, 'rb') as f:
            return f.read()
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)
        if os.path.exists(mp3_path):
            os.unlink(mp3_path)
