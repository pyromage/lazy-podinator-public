"""Audio generation: TTS (Kokoro or Piper), pronunciation fixes, MP3 conversion."""

import os
import subprocess
import tempfile

from config import (
    load_json_config, TTS_ENGINE,
    KOKORO_MODEL_PATH, KOKORO_VOICES_PATH,
    PIPER_PATH, MODELS_PATH,
)


# Pronunciation guide cache
_pronunciation_guide = None

# Kokoro model is loaded once and reused across shows
_kokoro = None

# Maps the Piper voice names stored in shows_config.json to Kokoro voices, so
# existing configs work unchanged when TTS_ENGINE=kokoro. Any voice name not in
# this map is passed through to Kokoro as-is (use native names like "am_adam").
KOKORO_VOICE_MAP = {
    "en_US-ryan-high": "am_michael",   # deep, authoritative male
    "en_US-amy-medium": "af_heart",    # energetic female
}
KOKORO_SPEED = float(os.environ.get("KOKORO_SPEED", "1.0"))


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
    """Replace difficult words with TTS-friendly respellings before synthesis."""
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


def _load_kokoro():
    """Lazily load and cache the Kokoro ONNX model (reused across shows)."""
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        print(f"Loading Kokoro model: {KOKORO_MODEL_PATH}")
        _kokoro = Kokoro(KOKORO_MODEL_PATH, KOKORO_VOICES_PATH)
    return _kokoro


def _generate_kokoro_wav(text, voice_model, wav_path):
    """Synthesize speech with Kokoro and write a WAV file."""
    import soundfile as sf
    kokoro = _load_kokoro()
    voice = KOKORO_VOICE_MAP.get(voice_model, voice_model)
    samples, sample_rate = kokoro.create(
        text, voice=voice, speed=KOKORO_SPEED, lang="en-us")
    sf.write(wav_path, samples, sample_rate)
    print(f"Kokoro generated {len(samples) / sample_rate:.1f}s (voice: {voice})")


def _generate_piper_wav(text, voice_model, wav_path):
    """Synthesize speech with Piper TTS and write a WAV file."""
    model_path = os.path.join(MODELS_PATH, f"{voice_model}.onnx")
    config_path = os.path.join(MODELS_PATH, f"{voice_model}.onnx.json")
    process = subprocess.run(
        [
            PIPER_PATH,
            "--model", model_path,
            "--config", config_path,
            "--length-scale", "1.1",
            "--sentence-silence", "0.8",
            "--output_file", wav_path
        ],
        input=text.encode('utf-8'),
        capture_output=True,
        check=True
    )
    print(f"Piper output: {process.stderr.decode()}")


def generate_audio(script_text, voice_model, show_key=None):
    """Convert a script to MP3 using the configured TTS engine, with natural pacing."""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file:
        wav_path = wav_file.name

    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as mp3_file:
        mp3_path = mp3_file.name

    try:
        cleaned_text = script_text.replace("[PAUSE]", "").replace("...", ".")
        cleaned_text = apply_pronunciation_fixes(cleaned_text, show_key=show_key)

        if TTS_ENGINE == "piper":
            _generate_piper_wav(cleaned_text, voice_model, wav_path)
        else:
            _generate_kokoro_wav(cleaned_text, voice_model, wav_path)

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
