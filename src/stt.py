import os

from groq import BadRequestError, Groq

# Groq's hosted whisper-large-v3-turbo, not a local model - swapped in 2026-08-08 after live
# testing showed the previous local faster-whisper "small" model badly garbling real Pakistani
# speech (nonsense transcriptions, occasional hallucinated foreign-language text on noisy audio)
# and struggling with Urdu/English code-switching ("kya apka paas class 10 hai"-style sentences).
# large-v3-turbo is dramatically more accurate at both, runs on Groq's hardware (no local GPU
# needed - also removes a hosting blocker), and is already free-tier covered by the same
# GROQ_API_KEY the LLM catalog uses.
MODEL = "whisper-large-v3-turbo"

# Whisper prompts are a soft decoding bias, not a hard instruction, but they measurably help
# it settle on natural code-switched transcriptions instead of "correcting" English words into
# nearby-sounding Urdu ones.
PROMPT = (
    "گفتگو، اردو کسٹمر سپورٹ کال۔ لوگ اکثر انگریزی الفاظ اردو جملوں میں ملا کر بولتے ہیں، "
    "جیسے 'class 10', 'discount', 'order' - انہیں جیسے بولا گیا ویسے ہی لکھیں۔"
)

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


class Transcriber:
    def transcribe(self, wav_path: str, reply_language: str = "auto") -> str:
        # "auto" lets Whisper detect the spoken language per-utterance (needed for clean
        # English transcription); "urdu"/"english" hint the language explicitly, which is
        # more reliable for short utterances (Whisper's auto-detect confuses Urdu/Hindi).
        whisper_language = {"urdu": "ur", "english": "en"}.get(reply_language)
        try:
            with open(wav_path, "rb") as f:
                kwargs = {"file": (os.path.basename(wav_path), f.read()), "model": MODEL, "prompt": PROMPT}
                if whisper_language:
                    kwargs["language"] = whisper_language
                try:
                    result = _get_client().audio.transcriptions.create(**kwargs)
                except BadRequestError as e:
                    # A hold too brief to capture real speech (a quick tap rather than a held
                    # button) produces a near-empty wav - Groq rejects anything under 0.01s.
                    # Treat it the same as "no speech detected", not a crash.
                    if "too short" in str(e).lower():
                        return ""
                    raise
        finally:
            os.unlink(wav_path)
        return result.text.strip()
