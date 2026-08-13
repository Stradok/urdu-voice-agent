"""Real-time voice calls via LiveKit Agents - the transport/orchestration layer for genuine
two-way conversation (VAD-driven turn-taking, barge-in interruption), separate from the
hold-to-talk async voice-message flow in src/voice/mic.py. A standalone worker process
(src/realtime/worker.py), not a FastAPI endpoint - run it directly, it connects out to
LiveKit Cloud rather than accepting inbound HTTP requests.

Reuses src/agent/'s ChatEngine/tools/persona as-is (see worker.py's SaraAgent.llm_node) -
this package is purely the real-time plumbing LiveKit provides on top, not a rewrite of the
conversation logic.
"""
