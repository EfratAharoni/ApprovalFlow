"""
Hybrid policy retrieval — BM25 + vector search fused 50/50.

Why hybrid: BM25 handles keyword overlap ("alcohol" → MEAL-03);
vector handles semantic drift ("happy hour beverages" → MEAL-03).
Either alone misses one of these cases (documented in ADR-008).
"""
from __future__ import annotations

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from .policy import POLICY_RULES

_model = SentenceTransformer("all-MiniLM-L6-v2")

POLICY_CHUNKS: list[dict] = [
    {"id": rule_id, "text": text}
    for rule_id, text in POLICY_RULES.items()
]


class PolicyIndex:
    def __init__(self, chunks: list[dict] | None = None):
        self.chunks = chunks if chunks is not None else POLICY_CHUNKS
        texts = [c["text"] for c in self.chunks]

        # Vector index — cast to ndarray so mypy can verify @ operator usage
        self.embeddings: np.ndarray = np.array(_model.encode(texts))

        # BM25 index
        tokenized = [t.lower().split() for t in texts]
        self.bm25 = BM25Okapi(tokenized)

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        # Vector scores — cast to ndarray so mypy can verify @ operator usage
        q_emb: np.ndarray = np.array(_model.encode([query])[0])
        norms = np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(q_emb)
        vector_scores = np.array(self.embeddings @ q_emb) / np.where(norms == 0, 1e-9, norms)

        # BM25 scores
        bm25_scores = np.array(self.bm25.get_scores(query.lower().split()))

        def _normalize(arr: np.ndarray) -> np.ndarray:
            mn, mx = arr.min(), arr.max()
            if mx == mn:
                return np.zeros_like(arr)
            return (arr - mn) / (mx - mn)

        combined = 0.5 * _normalize(vector_scores) + 0.5 * _normalize(bm25_scores)

        top_indices = np.argsort(combined)[-top_k:][::-1]
        return [
            {**self.chunks[i], "score": float(combined[i])}
            for i in top_indices
        ]


# Module-level singleton — built once at import time, reused across requests.
policy_index = PolicyIndex()
