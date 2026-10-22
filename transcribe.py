"""Transcribe a sermon video on this computer. Nothing is uploaded."""

import os
import subprocess
import wave
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

import paths

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

MODEL_DIR = paths.user_dir() / "data" / "models"
MODELS = {
    "standard": "small.en",
    "high": "distil-large-v3",
}


def load_audio(path):
    wav_path = Path(path).with_suffix(".16k.wav")
    subprocess.run(
        [paths.ffmpeg_cmd(), "-y", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "wav", str(wav_path)],
        check=True, capture_output=True,
    )
    with wave.open(str(wav_path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
    wav_path.unlink(missing_ok=True)
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(path, accuracy, on_status):
    model_name = MODELS.get(accuracy, MODELS["high"])
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    on_status(f"Loading the {model_name} speech model. The first time, it downloads and stays on this computer.")
    model = WhisperModel(
        model_name,
        device="cpu",
        compute_type="int8",
        download_root=str(MODEL_DIR),
    )
    on_status("Reading the audio.")
    audio = load_audio(path)
    duration = len(audio) / 16000
    on_status("Transcribing. A full sermon can take about as long as the recording on this PC.")
    segments, _info = model.transcribe(
        audio,
        language="en",
        vad_filter=True,
        beam_size=5,
        word_timestamps=False,
        initial_prompt="A pastor preaching a sermon and citing Scripture.",
    )
    spoken = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        spoken.append({"start": segment.start, "end": segment.end, "text": text})
        if duration:
            done = min(99, int(segment.end / duration * 100))
            on_status(f"Transcribing… {done}%")
    on_status("Transcribing… 100%")
    return spoken
