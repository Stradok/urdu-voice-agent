"""LiveKit Agents worker - the real-time voice call entry point. A separate long-running
process from the FastAPI app (src/api.py), not a new endpoint on it. Run directly:

    .venv/bin/python -m src.realtime.worker dev

It connects *out* to LiveKit Cloud (no inbound ports to expose), waits for room dispatch,
and handles one call per job. Reuses src/agent/llm.py's ChatEngine as-is for the actual
conversation logic (persona, FAQ retrieval, tool-calling, language handling) - this file is
purely the transport/orchestration layer LiveKit Agents adds on top: VAD-driven turn-taking
and barge-in/interruption handling, neither of which the hold-to-talk path has or needs.
"""
import asyncio
import logging
import os
import random
import re
from collections.abc import AsyncIterator

from dotenv import load_dotenv

load_dotenv()

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    ModelSettings,
    WorkerOptions,
    cli,
    llm,
)
from livekit.plugins import silero

from .providers import resolve_providers
from .tenant import resolve_tenant
from ..agent.faq_store import FaqStore
from ..agent.llm import ChatEngine
from ..business_context import BusinessContext
from ..data import settings as app_settings

logger = logging.getLogger("livekit.agents")

# Spoken while a tool call (Postgres lookup + a follow-up LLM round-trip) is in flight - see
# SaraAgent._on_tool_call. Several options per language, picked at random, so a multi-tool
# conversation doesn't hear the exact same filler every time. Elongated letters (2026-08-10,
# user's own idea) mimic how a real human agent verbally stalls while looking something up
# ("Okaaay, let meee seee...") instead of a flat, clipped phrase followed by dead silence -
# how reliably a TTS engine actually renders repeated letters as a drawn-out sound (versus
# just collapsing them back to normal, or something more clipped) hasn't been verified yet,
# needs a real listen with the current provider (Cartesia for English, Azure for Urdu) before
# trusting this fully - the letter-repetition trick isn't standardized TTS behavior.
FILLER_PHRASES = {
    "english": [
        "Okaaay, let meee seee...", "Hmmm, one mooment, checking...", "Okaaay... let's seee what we've got heeere...",
    ],
    "urdu": ["ٹھیک ہےےے، ذرا چیک کرتیییی ہوں...", "ایک منٹٹٹ، دیکھتیییی ہوں...", "بسسس ایک لمحہہہ..."],
    "roman_urdu": ["Ekkk second, dekhtiii hoon...", "Theeek hai, check kartiii hoon...", "Bassss ek lamhaaa..."],
}

# Spoken once, immediately when a call connects (entrypoint below) - via session.say(), same
# mechanism as the filler phrases, not routed through ChatEngine/the LLM: there's no user
# message yet for llm_node's _last_user_text to find, and a call-opening greeting is a fixed
# line anyway, not something that benefits from per-turn reasoning. Matters for correctness,
# not just politeness - live testing 2026-08-10 found the model mishandling a customer's bare
# "Hello? Can you hear me?" as the conversation's opening line (no prior context to anchor on);
# having Sara speak first means the customer's first turn is a real answer to a real question
# instead of an ambiguous opener.
GREETINGS = {
    "english": "Hello! How can I help you today?",
    "urdu": "السلام علیکم! میں آپ کی کیا مدد کر سکتی ہوں؟",
    "roman_urdu": "Assalam-o-alaikum! Main aap ki kya madad kar sakti hoon?",
}

_URDU_SCRIPT_RE = re.compile(r"[؀-ۿ]")


def _pick_filler_phrases(reply_language: str, user_text: str) -> list[str]:
    """A business set to "auto" matches whatever language the customer just used for the real
    reply too (agent/llm.py's LANGUAGE_MODE_INSTRUCTIONS) - but the filler fires *before* any
    LLM call returns, so there's no model output to key off, only the just-transcribed
    user_text. Live bug this fixes (2026-08-10): "auto" used to map straight to the Urdu
    pool, so a customer speaking English got a real English reply but an Urdu-script filler -
    a jarring mismatch. Urdu-script presence is a reliable per-turn signal; anything without
    it (English or Roman Urdu - both Latin script, not reliably distinguishable by a quick
    regex) falls back to the Roman Urdu pool, since a short Roman Urdu phrase still reads fine
    to an English speaker, whereas Urdu *script* would be opaque to one. Non-"auto" businesses
    already told us their one language - no per-turn detection needed."""
    if reply_language != "auto":
        return FILLER_PHRASES.get(reply_language, FILLER_PHRASES["roman_urdu"])
    if _URDU_SCRIPT_RE.search(user_text):
        return FILLER_PHRASES["urdu"]
    return FILLER_PHRASES["roman_urdu"]


def prewarm(proc: JobProcess) -> None:
    """Runs once when a worker subprocess spins up, before it's handed any job - LiveKit's
    hook for expensive one-time setup (see WorkerOptions.prewarm_fnc). Loading the FaqStore's
    embedding model and Silero's VAD model here (instead of at plain module-import time or
    inside entrypoint()) matters because num_idle_processes below keeps a spare subprocess
    pre-warmed ahead of any job arriving - so this cost is paid once, off the critical path,
    rather than inside the 10s-ish initialize_process_timeout window a real call is waiting on.
    """
    proc.userdata["faq_store"] = FaqStore()
    proc.userdata["vad"] = silero.VAD.load()


def _last_user_text(chat_ctx: llm.ChatContext) -> str:
    for item in reversed(chat_ctx.items):
        if getattr(item, "role", None) == "user":
            return item.text_content
    return ""


class _NullLLM(llm.LLM):
    """A real reply never comes from here - SaraAgent.llm_node overrides the reply path
    entirely, so chat() is never invoked. This class exists only because AgentActivity
    silently skips reply generation whenever `self.llm is None` (agent_activity.py's
    _user_turn_completed_task: `elif self.llm is None: return`) - that check runs *before*
    llm_node is ever called, has no idea llm_node is overridden, and fails with no exception
    and no log line. Confirmed live: STT/VAD/turn-detection all worked, "user turn committed"
    fired repeatedly, and Sara never replied - because no `llm=` had been passed anywhere.
    """

    def chat(self, *, chat_ctx, tools=None, conn_options=None, **kwargs):
        raise NotImplementedError("SaraAgent.llm_node overrides the reply path - chat() should never run")


_NULL_LLM = _NullLLM()


class SaraAgent(Agent):
    """One instance per call/room. business_id is resolved once at construction (a room
    belongs to exactly one business for its whole lifetime) - unlike src/api.py's
    _chat_engines dict, which caches one ChatEngine per business because a single FastAPI
    process serves many businesses concurrently over HTTP; here, one Agent instance already
    *is* scoped to one call."""

    def __init__(self, business: BusinessContext, faq_store: FaqStore, reply_language: str):
        # ChatEngine builds its own system prompt fresh every turn (src/agent/persona.py's
        # build_system_prompt) - this base `instructions` field is unused, llm_node below
        # bypasses AgentSession's own LLM invocation entirely. llm=_NULL_LLM is required
        # anyway - see _NullLLM's docstring for why.
        super().__init__(instructions="", llm=_NULL_LLM)
        self._reply_language = reply_language
        self._engine = ChatEngine(
            faq_store=faq_store, business_id=business.id, business_type=business.business_type,
            on_tool_call=self._on_tool_call,
        )

    def _on_tool_call(self, user_text: str) -> str:
        # Just returns text now - no thread-crossing needed. reply_stream() (agent/llm.py)
        # calls this directly and yields the result as part of its own stream, in the same
        # background thread llm_node already runs that stream on - see ChatEngine.__init__'s
        # on_tool_call docstring for why an earlier version that spoke this out-of-band via
        # session.say() reordered audio (real reply, then the filler) once llm_node became a
        # stream instead of a single blocking call.
        phrases = _pick_filler_phrases(self._reply_language, user_text)
        phrase = random.choice(phrases)
        logger.debug("using filler while tool call runs", extra={"phrase": phrase})
        return phrase

    async def llm_node(
        self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings: ModelSettings,
    ) -> AsyncIterator[str]:
        # ChatEngine.reply_stream() is a synchronous generator (see agent/llm.py) - runs on a
        # background thread via loop.run_in_executor so it doesn't block the event loop (VAD,
        # audio I/O) while the LLM/tools are running, same reasoning the old asyncio.to_thread
        # single-call version had. Chunks cross the thread boundary through an asyncio.Queue,
        # handed off via call_soon_threadsafe (asyncio.Queue.put_nowait isn't safe to call
        # directly from another thread) - the same cross-thread pattern _on_tool_call already
        # uses for the filler phrase. Confirmed against the real installed SDK that llm_node
        # supports returning an AsyncIterable[str], not just a single Coroutine[..., str] -
        # this is genuine token streaming (TTS starts on the first chunk), not a workaround,
        # for the plain-reply case; a tool-calling turn still yields one final chunk (see
        # reply_stream's docstring for why that path deliberately doesn't stream).
        user_text = _last_user_text(chat_ctx)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        _DONE = object()

        def _run() -> None:
            try:
                for piece in self._engine.reply_stream(user_text):
                    loop.call_soon_threadsafe(queue.put_nowait, piece)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, _DONE)

        loop.run_in_executor(None, _run)

        while True:
            item = await queue.get()
            if item is _DONE:
                return
            if isinstance(item, Exception):
                raise item
            yield item


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    business = resolve_tenant(ctx)
    reply_language = app_settings.load_settings(business.id)["reply_language"]
    live_stt, live_tts = resolve_providers(reply_language)

    session = AgentSession(
        stt=live_stt, tts=live_tts, vad=ctx.proc.userdata["vad"],
        # Tuned 2026-08-10 after live testing showed default 0.5s interruption min_duration
        # ate the first ~half-second of real barge-in speech (Sara kept talking over it while
        # deciding whether it was a real interruption or noise). Lowered to react faster;
        # resume_false_interruption (default True) is the existing safety net if this now
        # over-triggers on stray noise - not disabled, just leaning the other way.
        # endpointing max_delay: defaults to 2.5s (turn-detector-v1 counts as a "streaming"
        # turn detector, see livekit's turn.py _STREAMING_ENDPOINTING_DEFAULTS) - live logs
        # showed short/ambiguous utterances ("Okay.", "حالو!") getting low model confidence
        # and eating the full 2.5s before Sara would respond. Lowered the ceiling - real
        # tradeoff: more risk of cutting someone off mid-sentence on a short utterance, traded
        # for not waiting 2.5s every time the model is merely unsure.
        turn_handling={
            "interruption": {"min_duration": 0.2},
            "endpointing": {"max_delay": 1.5},
            # Enabled by default in AgentSession - explicitly OFF here. Preemptive generation
            # calls the same _generate_reply -> llm_node path a normal turn uses, but on
            # interim/unconfirmed transcripts before the turn commits, discarding the result
            # if the final transcript doesn't match. That's safe for a framework whose LLM
            # only *decides* to call a tool - it's not safe for us: SaraAgent.llm_node calls
            # ChatEngine.reply(), which actually *executes* tools (real Postgres writes,
            # including book_appointment) as part of generating the text, not after it's
            # confirmed. A discarded speculative generation would still have booked a real
            # appointment based on words the customer never actually finished saying. Leave
            # off until tool execution is redesigned to gate on a confirmed turn, not a
            # generation attempt - see plan.md's pipeline-overhaul section, 2026-08-10.
            "preemptive_generation": {"enabled": False},
        },
    )
    agent = SaraAgent(business, ctx.proc.userdata["faq_store"], reply_language)
    await session.start(agent=agent, room=ctx.room)

    # "auto" defaults to Urdu, same reasoning as agent/llm.py's FALLBACK_REPLIES - there's no
    # customer text yet to detect a script from (unlike the filler phrases, which react to
    # something the customer already said), so this has to be a static per-language choice.
    greeting = GREETINGS.get(reply_language, GREETINGS["urdu"])
    session.say(greeting, allow_interruptions=True)


if __name__ == "__main__":
    # agent_name enables *explicit* dispatch (LiveKit's own recommendation for anything more
    # than the simplest demo) - a room only gets this agent if a caller specifically asks for
    # "sara" by name, rather than every room in the project auto-dispatching one.
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm,
        # Dev mode defaults to 0 idle processes (fine for hot-reload workflows, wrong for a
        # real call - it means every job cold-spawns a subprocess that has to import torch/
        # sentence-transformers/sqlalchemy from scratch inside initialize_process_timeout).
        # Forcing 1 keeps a spare subprocess pre-warmed (prewarm() already run) so a dispatched
        # job attaches to it immediately instead of racing a cold import against the timeout -
        # this is what actually fixed the repeated "process initialization timed out" failures
        # seen live against LiveKit Cloud (traceback: ipc/supervised_proc.py's initialize()).
        num_idle_processes=1,
        # Generous headroom for the *first* subprocess (worker startup, no idle spare to have
        # already absorbed the cold-import cost yet) - 10s default was too tight for this
        # project's torch/sentence-transformers import chain, observed timing out at exactly
        # 10s across three consecutive attempts before this fix.
        initialize_process_timeout=60.0,
        agent_name="sara",
        ws_url=os.environ.get("LIVEKIT_URL"),
        api_key=os.environ.get("LIVEKIT_API_KEY"),
        api_secret=os.environ.get("LIVEKIT_API_SECRET"),
    ))
