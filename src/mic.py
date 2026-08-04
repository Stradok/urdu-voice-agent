import subprocess
import tempfile
import os

SAMPLE_RATE = 16000


def record(seconds: float = 5.0) -> str:
    """Record from the default mic via arecord, return path to a 16kHz mono wav file."""
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    subprocess.run(
        [
            "arecord", "-q",
            "-f", "S16_LE",
            "-r", str(SAMPLE_RATE),
            "-c", "1",
            "-d", str(seconds),
            path,
        ],
        check=True,
    )
    return path
