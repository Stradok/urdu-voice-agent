import os

from faster_whisper import WhisperModel


class Transcriber:
    def __init__(self, model_size: str = "small", device: str = "cuda", compute_type: str = "float16"):
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, wav_path: str) -> str:
        segments, _ = self.model.transcribe(wav_path, language="ur")
        text = "".join(segment.text for segment in segments).strip()
        os.unlink(wav_path)
        return text
