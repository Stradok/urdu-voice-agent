import os
import subprocess
import tempfile
import wave

import webrtcvad

from . import settings as app_settings
from .audio_devices import resolve_capture_device

SAMPLE_RATE = 16000
FRAME_MS = 30  # webrtcvad only accepts 10/20/30ms frames
FRAME_BYTES = int(SAMPLE_RATE * (FRAME_MS / 1000.0) * 2)  # 16-bit mono PCM

MAX_SECONDS = 12.0  # hard cap in case VAD never detects silence
VAD_AGGRESSIVENESS = 2  # 0 (lenient) - 3 (strict about filtering non-speech)


def record(max_seconds: float = MAX_SECONDS) -> str:
    """Record from the mic until the speaker goes quiet (VAD-based), return path to a 16kHz mono wav file."""
    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
    device = resolve_capture_device(app_settings.load_settings()["mic_device"])
    proc = subprocess.Popen(
        ["arecord", "-q", "-D", device, "-t", "raw", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1"],
        stdout=subprocess.PIPE,
    )

    silence_tail_ms = app_settings.load_settings()["vad_silence_ms"]
    frames = []
    silence_frames_needed = int(silence_tail_ms / FRAME_MS)
    trailing_silence = 0
    speech_started = False
    max_frames = int((max_seconds * 1000) / FRAME_MS)

    try:
        for _ in range(max_frames):
            frame = proc.stdout.read(FRAME_BYTES)
            if len(frame) < FRAME_BYTES:
                break
            frames.append(frame)

            if vad.is_speech(frame, SAMPLE_RATE):
                speech_started = True
                trailing_silence = 0
            elif speech_started:
                trailing_silence += 1
                if trailing_silence >= silence_frames_needed:
                    break
    finally:
        proc.terminate()
        proc.wait()

    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))

    return path
