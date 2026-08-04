import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

FAQ_PATH = Path(__file__).resolve().parent.parent / "data" / "faq" / "faq.json"
CHROMA_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma"

# Similarity below this means "not an FAQ match" -> fall back to free conversation.
# Chroma returns cosine distance (0 = identical, 2 = opposite); tune after testing.
MATCH_DISTANCE_THRESHOLD = 0.22


class FaqStore:
    def __init__(self, embed_model_name: str = "intfloat/multilingual-e5-small", device: str = "cuda"):
        self.embedder = SentenceTransformer(embed_model_name, device=device)
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = self.client.get_or_create_collection("faq")
        self._sync_from_json()

    def _sync_from_json(self):
        with open(FAQ_PATH, encoding="utf-8") as f:
            entries = json.load(f)

        existing_ids = set(self.collection.get()["ids"])
        wanted_ids = {e["id"] for e in entries}

        # Remove entries deleted from faq.json
        stale = existing_ids - wanted_ids
        if stale:
            self.collection.delete(ids=list(stale))

        new_entries = [e for e in entries if e["id"] not in existing_ids]
        if new_entries:
            questions = ["passage: " + e["question"] for e in new_entries]
            embeddings = self.embedder.encode(questions, normalize_embeddings=True).tolist()
            self.collection.add(
                ids=[e["id"] for e in new_entries],
                embeddings=embeddings,
                documents=[e["answer"] for e in new_entries],
                metadatas=[{"question": e["question"]} for e in new_entries],
            )

    def search(self, query: str):
        """Return (answer, distance) for the closest FAQ match, or (None, None) if store is empty."""
        query_emb = self.embedder.encode(["query: " + query], normalize_embeddings=True).tolist()
        result = self.collection.query(query_embeddings=query_emb, n_results=1)
        if not result["documents"] or not result["documents"][0]:
            return None, None
        return result["documents"][0][0], result["distances"][0][0]

    def get_context(self, query: str):
        """Return FAQ answer text to ground the LLM on, or None if the query doesn't match any FAQ closely enough."""
        answer, distance = self.search(query)
        if answer is None or distance > MATCH_DISTANCE_THRESHOLD:
            return None
        return answer
