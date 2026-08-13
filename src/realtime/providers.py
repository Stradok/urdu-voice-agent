"""Per-language STT/TTS provider selection for live calls.

A live call's STT provider has to be chosen *before* any transcription happens - unlike
src/agent/llm.py's LANGUAGE_MODE_INSTRUCTIONS (which can pick a reply-language instruction
after the fact, once typed/transcribed text already exists), there's no "auto-detect the
language, then pick STT" available here. Resolution: use the same AppSettings.reply_language
every business already has, resolved once per call session, not per-utterance.

Urdu path (auto/urdu/roman_urdu - the Pakistan-market default): Groq STT + Azure TTS, the
exact providers already proven for Urdu/code-switching this session (src/voice/stt.py,
src/voice/tts.py) - reused here via their LiveKit plugin equivalents rather than the
project's own one-shot wrapper classes, since AgentSession expects the streaming/concurrent
shape the plugins are built for, not a blocking request/response call.

English path (reply_language == "english" - a business that has explicitly opted into
English-only, e.g. a future US-enterprise client, so there's no Urdu code-switching exposure
to risk): Deepgram Nova-3 STT + Cartesia Sonic-3 TTS, via LiveKit Inference rather than calling
Deepgram/Cartesia directly - same underlying models, but LiveKit's own docs and third-party
benchmarks (2026-08-10 research, see plan.md's pipeline-overhaul section) both point to
LiveKit Inference's provider connections being co-located with the SFU our worker already
talks to, cutting the cross-region network hop a direct call from our worker would otherwise
pay on every utterance/reply - the same class of latency cost found and left unfixed for
Azure TTS earlier (Mumbai worker vs uaenorth Azure). inference.STT/inference.TTS are genuine
livekit.agents.stt.STT/tts.TTS subclasses (confirmed via their actual MRO, not assumed) - true
drop-in replacements for the plugin classes, nothing else in this file or worker.py needs to
change. Billed against LiveKit Cloud's own inference credits (LIVEKIT_API_KEY/API_SECRET,
already required for everything else here) - DEEPGRAM_API_KEY/CARTESIA_API_KEY are no longer
needed for this path. Both models were disqualified for the Urdu path this project actually
ships (Deepgram measured 100% WER on Urdu, Cartesia's Urdu support was never separately
verified for TTS) - neither concern applies here since this path never sees Urdu at all. The
LLM for this path is chosen separately, per-business, via the normal AppSettings.llm_model /
LLM_CATALOG mechanism in agent/llm.py - see worker.py's entrypoint.
"""
import os

from livekit.agents import inference, stt, tts
from livekit.plugins import azure, groq

from ..voice.stt import PROMPT as GROQ_STT_PROMPT
from ..voice.tts import VOICE as AZURE_TTS_VOICE


def resolve_providers(reply_language: str) -> tuple[stt.STT, tts.TTS]:
    if reply_language == "english":
        live_stt = inference.STT(
            model="deepgram/nova-3",
            api_key=os.environ["LIVEKIT_API_KEY"], api_secret=os.environ["LIVEKIT_API_SECRET"],
        )
        live_tts = inference.TTS(
            model="cartesia/sonic-3",
            api_key=os.environ["LIVEKIT_API_KEY"], api_secret=os.environ["LIVEKIT_API_SECRET"],
        )
        return live_stt, live_tts

    # auto / urdu / roman_urdu all use the same Urdu-proven providers. detect_language=True
    # (verified against the installed plugin's actual source, not assumed) makes the STT
    # ignore its own language="en" default and auto-detect per utterance - the same
    # code-switching handling already proven for the async voice-message path, just live.
    live_stt = groq.STT(
        model="whisper-large-v3-turbo",
        api_key=os.environ["GROQ_API_KEY"],
        prompt=GROQ_STT_PROMPT,
        detect_language=True,
    )
    live_tts = azure.TTS(
        voice=AZURE_TTS_VOICE,
        speech_key=os.environ["AZURE_SPEECH_KEY"],
        speech_region=os.environ["AZURE_SPEECH_REGION"],
    )
    return live_stt, live_tts
