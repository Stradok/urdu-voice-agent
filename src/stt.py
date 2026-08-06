import os

# Shared across all projects on this machine (see `pip install --target` in project setup notes)
# so CUDA-12 libs are downloaded once instead of per-venv.
CUDA12_LIBS_DIR = os.path.expanduser("~/.local/share/nvidia-cuda12-libs")


def _add_cuda12_libs_to_ld_path():
    """ctranslate2 (faster-whisper's backend) dynamically links CUDA 12's cuBLAS/cuDNN,
    but this machine's driver/toolkit are CUDA 13. Point it at the cu12 wheels instead."""
    cublas_dir = os.path.join(CUDA12_LIBS_DIR, "nvidia", "cublas", "lib")
    cudnn_dir = os.path.join(CUDA12_LIBS_DIR, "nvidia", "cudnn", "lib")
    if not (os.path.isdir(cublas_dir) and os.path.isdir(cudnn_dir)):
        return
    existing = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = ":".join([cublas_dir, cudnn_dir] + ([existing] if existing else []))


_add_cuda12_libs_to_ld_path()

from faster_whisper import WhisperModel


class Transcriber:
    def __init__(self, model_size: str = "small", device: str = "cuda", compute_type: str = "float16"):
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, wav_path: str) -> str:
        segments, _ = self.model.transcribe(wav_path, language="ur")
        text = "".join(segment.text for segment in segments).strip()
        os.unlink(wav_path)
        return text
