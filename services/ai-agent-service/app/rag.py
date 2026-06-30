"""
RAG (Retrieval-Augmented Generation) module — semantic search over policy rules.

Model: sentence-transformers/all-MiniLM-L6-v2 (free, local, no API key required).
First run downloads ~90 MB from HuggingFace Hub; cached at SENTENCE_TRANSFORMERS_HOME.
Embeddings are computed once at startup and held in memory.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TypedDict

import numpy as np
from sentence_transformers import SentenceTransformer

from .policy import POLICY_RULES

logger = logging.getLogger(__name__)

# All real policy rules — SYSTEM-ERROR is a synthetic fallback message, not a reimbursement rule
_INDEXABLE_IDS: list[str] = [rid for rid in POLICY_RULES if rid != "SYSTEM-ERROR"]


@dataclass(frozen=True)
class PolicyChunk:
    rule_id: str
    text: str


class SearchResult(TypedDict):
    rule_id: str
    text: str
    score: float


def _build_chunks() -> list[PolicyChunk]:
    return [PolicyChunk(rule_id=rid, text=POLICY_RULES[rid]) for rid in _INDEXABLE_IDS]


class PolicyIndex:
    """Holds sentence-transformer embeddings for all policy chunks."""

    def __init__(self) -> None:
        logger.info("loading sentence-transformer model (all-MiniLM-L6-v2)")
        self._model = SentenceTransformer("all-MiniLM-L6-v2")
        self._chunks = _build_chunks()
        texts = [c.text for c in self._chunks]
        self._embeddings: np.ndarray = self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        logger.info("policy index ready", extra={"chunks": len(self._chunks)})

    def search(self, query: str, top_k: int = 3) -> list[SearchResult]:
        """Return top-k chunks most relevant to query via cosine similarity."""
        q_vec: np.ndarray = self._model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        )[0]
        # dot product of L2-normalized vectors = cosine similarity
        scores: np.ndarray = self._embeddings @ q_vec
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [
            SearchResult(
                rule_id=self._chunks[i].rule_id,
                text=self._chunks[i].text,
                score=float(scores[i]),
            )
            for i in top_indices
        ]


_index: PolicyIndex | None = None


def _get_index() -> PolicyIndex:
    global _index
    if _index is None:
        _index = PolicyIndex()
    return _index


def preload_index() -> None:
    """Force-initialize the index at startup (avoids cold-start latency on first request)."""
    _get_index()


def search_policy(query: str, top_k: int = 3) -> list[SearchResult]:
    """Return top-k policy chunks most semantically relevant to query."""
    return _get_index().search(query, top_k=top_k)
