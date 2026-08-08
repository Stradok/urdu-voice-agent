from uuid import UUID

from sentence_transformers import SentenceTransformer
from sqlalchemy import select

from .db import get_session
from .models import FaqEntry

# Similarity below this means "not an FAQ match" -> fall back to free conversation.
# pgvector's cosine_distance is 1 - cosine_similarity (0 = identical, 2 = opposite) -
# same definition Chroma used, so this threshold carries over unchanged.
MATCH_DISTANCE_THRESHOLD = 0.22
# How many close matches to hand the LLM, not just the single closest - see get_context.
FAQ_TOP_K = 3


class FaqStore:
    def __init__(self, embed_model_name: str = "intfloat/multilingual-e5-small", device: str = "cuda"):
        self.embedder = SentenceTransformer(embed_model_name, device=device)

    def sync_embeddings(self, business_id: UUID):
        """Embed any FAQ entries for this business that don't have an embedding yet (new
        or just-edited via the FAQ page). Called after every FAQ write, not on every
        query, so a normal chat turn never pays for it."""
        with get_session() as session:
            entries = session.scalars(
                select(FaqEntry).where(FaqEntry.business_id == business_id, FaqEntry.embedding.is_(None))
            ).all()
            if not entries:
                return
            questions = ["passage: " + e.question for e in entries]
            embeddings = self.embedder.encode(questions, normalize_embeddings=True).tolist()
            for entry, embedding in zip(entries, embeddings):
                entry.embedding = embedding

    def get_context(self, business_id: UUID, query: str) -> str | None:
        """Return FAQ context to ground the LLM on, or None if nothing matches closely enough.

        Returns the top few matches within threshold, not just the single closest - two FAQs
        can sit within noise distance of each other. Observed live (2026-08-08): for a Roman-
        Urdu "clinic timings" query, "Where is the clinic located?" (distance 0.1385) narrowly
        beat "What are your clinic hours?" (0.1399) - a top-1-only query silently handed the
        LLM the address instead of the hours, with no signal a near-tied second candidate
        existed. Each match includes its own question alongside the answer so the model can
        judge which one actually answers what was asked, rather than trusting whichever
        embedding search ranked marginally first."""
        query_embedding = self.embedder.encode(["query: " + query], normalize_embeddings=True)[0].tolist()
        with get_session() as session:
            rows = session.execute(
                select(FaqEntry.question, FaqEntry.answer, FaqEntry.embedding.cosine_distance(query_embedding).label("distance"))
                .where(FaqEntry.business_id == business_id, FaqEntry.embedding.isnot(None))
                .order_by("distance")
                .limit(FAQ_TOP_K)
            ).all()
        matches = [row for row in rows if row.distance <= MATCH_DISTANCE_THRESHOLD]
        if not matches:
            return None
        return "\n".join(f"سوال: {m.question} | جواب: {m.answer}" for m in matches)
