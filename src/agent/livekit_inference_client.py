"""OpenAI-SDK-compatible wrapper around LiveKit Inference's LLM client
(livekit.agents.inference), so agent/llm.py's ChatEngine (_complete/_run_tool_calls/
_timed_completion/reply_stream) can use LiveKit Inference's models - Gemma 4 specifically,
chosen for its 192ms TTFT and serving-layer tool-call schema validation (see plan.md's
pipeline-overhaul section, 2026-08-10) - without any changes to that already-hardened
control-flow logic.

LiveKitInferenceClient.chat.completions.create(...) matches the OpenAI/Groq SDK shape closely
enough - same method nesting, same .choices[0].message.content/tool_calls response shape for
non-streaming, same .choices[0].delta.content/tool_calls shape for streaming - that
_complete()/_run_tool_calls()/_timed_completion() genuinely cannot tell the difference; it's a
drop-in "provider" alongside Groq/OpenRouter in _get_client().

Every shape used below (ChatContext.add_message/.insert, FunctionCall/FunctionCallOutput,
function_tool(raw_schema=...), LLMStream/.collect()/ChatChunk.delta) was verified against real,
live calls to the actual API before being written here (2026-08-10) - not assumed from docs.
"""
import asyncio
import queue
import threading

from livekit.agents import llm as lk_llm
from livekit.agents import inference


def _placeholder_tool_fn(**kwargs):
    raise RuntimeError(
        "never actually called - ChatEngine._run_tool_calls executes tools itself; this "
        "exists only because livekit's raw-schema Tool wrapper requires a callable"
    )


def _messages_to_chat_context(messages: list) -> lk_llm.ChatContext:
    """Converts ChatEngine's message list - a mix of plain OpenAI-style dicts (system/user/
    assistant/tool messages) and raw Groq/OpenAI SDK response objects (assistant messages with
    .tool_calls, appended directly by _run_tool_calls, see agent/llm.py) - into LiveKit's
    item-based ChatContext. LiveKit represents a tool round as two dedicated item types
    (FunctionCall, FunctionCallOutput), not plain role="assistant"/"tool" messages like the
    OpenAI shape does - confirmed via ChatContext's actual item union, not assumed."""
    ctx = lk_llm.ChatContext()
    for msg in messages:
        if isinstance(msg, dict):
            role = msg["role"]
            if role == "tool":
                ctx.insert(lk_llm.FunctionCallOutput(
                    call_id=msg["tool_call_id"], output=msg["content"], is_error=False,
                ))
            else:
                ctx.add_message(role=role, content=msg["content"])
        else:
            # raw SDK ChatCompletionMessage (an assistant turn with tool_calls, appended
            # directly by _run_tool_calls) - one FunctionCall item per tool call.
            if getattr(msg, "content", None):
                ctx.add_message(role="assistant", content=msg.content)
            for tc in (msg.tool_calls or []):
                ctx.insert(lk_llm.FunctionCall(
                    call_id=tc.id, name=tc.function.name, arguments=tc.function.arguments,
                ))
    return ctx


def _schemas_to_tools(tool_schemas: list[dict]) -> list:
    """tool_schemas_for()'s output is plain OpenAI function-calling JSON - {"type": "function",
    "function": {"name", "description", "parameters"}}. raw_schema= wants just the inner
    "function" dict (confirmed against RawFunctionDescription's actual required fields:
    name/description/parameters - the same three keys, no wrapper)."""
    return [
        lk_llm.function_tool(_placeholder_tool_fn, raw_schema=schema["function"])
        for schema in tool_schemas
    ]


def _convert_tool_calls(raw_tool_calls) -> list["_ToolCall"] | None:
    if not raw_tool_calls:
        return None
    return [_ToolCall(id=tc.call_id, name=tc.name, arguments=tc.arguments) for tc in raw_tool_calls]


class _ToolCallFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, id: str, name: str, arguments: str):
        self.id = id
        self.function = _ToolCallFunction(name, arguments)


class _Message:
    def __init__(self, content: str | None, tool_calls: list | None):
        self.content = content
        self.tool_calls = tool_calls


class _Delta:
    def __init__(self, content: str | None, tool_calls: list | None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, message: "_Message | None" = None, delta: "_Delta | None" = None):
        self.message = message
        self.delta = delta


class _Completion:
    def __init__(self, message: _Message):
        self.choices = [_Choice(message=message)]


class _Chunk:
    def __init__(self, content: str | None, tool_calls: list | None):
        self.choices = [_Choice(delta=_Delta(content, tool_calls))]


class _ChatCompletionsShim:
    def __init__(self, model_client: "inference.LLM"):
        self._model = model_client

    def create(
        self, *, model=None, messages, temperature=None, max_tokens=None,
        tools=None, tool_choice=None, stream=False,
    ):
        # model= is ignored - the real model is already fixed on the inference.LLM instance
        # this shim wraps (one LLM_CATALOG entry -> one LiveKitInferenceClient -> one model),
        # accepted as a kwarg only so _timed_completion's call signature doesn't need a
        # provider-specific branch.
        chat_ctx = _messages_to_chat_context(messages)
        lk_tools = _schemas_to_tools(tools) if tools else None
        if stream:
            return self._stream(chat_ctx, lk_tools)
        return asyncio.run(self._collect(chat_ctx, lk_tools))

    async def _collect(self, chat_ctx, lk_tools) -> _Completion:
        response = await self._model.chat(chat_ctx=chat_ctx, tools=lk_tools).collect()
        return _Completion(_Message(
            content=response.text or None,
            tool_calls=_convert_tool_calls(response.tool_calls),
        ))

    def _stream(self, chat_ctx, lk_tools):
        """A genuine synchronous generator - reply_stream() iterates this with a plain `for`,
        same as it already does for Groq/OpenAI's streaming responses. LiveKit's own stream is
        async-only, so this bridges it via a dedicated background thread running its own event
        loop, handing each chunk to this generator through a thread-safe queue.Queue as it
        arrives - deliberately NOT `asyncio.run()`-collecting the whole stream first and
        replaying it, which would silently defeat the entire point of reply_stream() (TTS
        starting on partial output) while still *looking* like a working iterator."""
        q: queue.Queue = queue.Queue()
        _DONE = object()

        def _run() -> None:
            async def _consume() -> None:
                try:
                    stream = self._model.chat(chat_ctx=chat_ctx, tools=lk_tools)
                    async for chat_chunk in stream:
                        content = chat_chunk.delta.content if chat_chunk.delta else None
                        tool_calls = _convert_tool_calls(
                            chat_chunk.delta.tool_calls if chat_chunk.delta else None
                        )
                        q.put(_Chunk(content, tool_calls))
                except Exception as e:  # surfaced to the consuming side below, not swallowed
                    q.put(e)
                finally:
                    q.put(_DONE)
            asyncio.run(_consume())

        threading.Thread(target=_run, daemon=True).start()

        while True:
            item = q.get()
            if item is _DONE:
                return
            if isinstance(item, Exception):
                raise item
            yield item


class LiveKitInferenceClient:
    """Constructed once per model (see agent/llm.py's _get_client) - mirrors the shape
    _get_client already returns for "groq"/"openrouter": an object with .chat.completions."""

    def __init__(self, model: str, api_key: str, api_secret: str):
        self._model = inference.LLM(model=model, api_key=api_key, api_secret=api_secret)
        self.chat = _Chat(self._model)


class _Chat:
    def __init__(self, model_client: "inference.LLM"):
        self.completions = _ChatCompletionsShim(model_client)
