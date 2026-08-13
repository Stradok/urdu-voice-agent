import os
import subprocess
import tempfile
import threading
import wave
from uuid import UUID

from ..data import settings as app_settings
from .audio_devices import resolve_capture_device

SAMPLE_RATE = 16000
CHUNK_BYTES = 4096
# Hard safety cap in case a client never sends stop (dropped connection, crashed tab) -
# without this a stuck recording would permanently block the single shared mic slot below.
MAX_SECONDS = 30.0


class _ActiveRecording:
    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self.frames: list[bytes] = []
        self._lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        while True:
            chunk = self.proc.stdout.read(CHUNK_BYTES)
            if not chunk:
                return
            with self._lock:
                self.frames.append(chunk)

    def stop(self) -> bytes:
        self.proc.terminate()
        self.proc.wait()
        self._reader.join(timeout=2)
        with self._lock:
            return b"".join(self.frames)


# Single shared mic slot - this is a local desktop app with one physical microphone, so one
# in-progress recording at a time is the natural model (not a per-business/per-request thing).
_active: _ActiveRecording | None = None
_active_lock = threading.Lock()


def start_recording(business_id: UUID):
    """Begin capturing from the mic. Call stop_recording() to get the wav back."""
    global _active
    with _active_lock:
        if _active is not None:
            raise RuntimeError("A recording is already in progress")
        device = resolve_capture_device(app_settings.load_settings(business_id)["mic_device"])
        proc = subprocess.Popen(
            ["arecord", "-q", "-D", device, "-t", "raw", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1"],
            stdout=subprocess.PIPE,
        )
        recording = _ActiveRecording(proc)
        _active = recording

    timer = threading.Timer(MAX_SECONDS, _watchdog_stop, args=(recording,))
    timer.daemon = True
    timer.start()


def _watchdog_stop(recording: "_ActiveRecording"):
    global _active
    with _active_lock:
        if _active is not recording:
            return  # already stopped normally
        _active = None
    recording.stop()  # discard - nothing is waiting to consume this audio


def stop_recording() -> str:
    """Stop the in-progress recording, return path to a 16kHz mono wav file."""
    global _active
    with _active_lock:
        if _active is None:
            raise RuntimeError("No recording in progress")
        recording = _active
        _active = None

    raw = recording.stop()
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(raw)
    return path
