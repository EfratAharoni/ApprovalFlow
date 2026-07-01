"""
Unit tests for PolicyIndex — hybrid BM25 + vector retrieval.

These tests run offline once the sentence-transformers model is cached locally
(downloaded automatically on first run via HuggingFace Hub).

Run: pytest services/ai-agent-service/tests/test_rag.py -v
"""
import pytest
from app.rag import PolicyIndex


@pytest.fixture(scope="module")
def index():
    return PolicyIndex()


def test_direct_alcohol_keyword_finds_meal03(index):
    """Strong keyword match: 'alcohol-only receipt' must surface MEAL-03 in top-3."""
    results = index.search("alcohol-only receipt", top_k=3)
    ids = [r["id"] for r in results]
    assert "MEAL-03" in ids, f"Expected MEAL-03 in top-3, got {ids}"


def test_happy_hour_beverages_finds_meal03(index):
    """
    Semantic drift case: 'team happy hour beverages' has no lexical overlap with
    MEAL-03's text ('Alcohol-only receipts are not reimbursable') but is semantically
    related. Hybrid retrieval must find MEAL-03 in top-3.

    This was an xfail with vector-only retrieval; it now passes with BM25 + vector fusion.
    """
    results = index.search("team happy hour beverages", top_k=3)
    ids = [r["id"] for r in results]
    assert "MEAL-03" in ids, (
        f"Hybrid retrieval failed the semantic-drift case — MEAL-03 not in top-3. Got: {ids}"
    )


def test_hybrid_beats_vector_only(index):
    """
    BM25 keyword path: 'alcohol-only bar expense' must rank MEAL-03 as top-1.

    The hyphenated token 'alcohol-only' is unique to MEAL-03's text
    ('Alcohol-only receipts are not reimbursable') so BM25 scores it very
    highly, lifting it above chunks that only match on common words.
    Vector-only retrieval cannot reliably achieve the same because the model
    may not assign MEAL-03 the highest cosine similarity for this phrasing.
    """
    results = index.search("alcohol-only bar expense", top_k=1)
    assert results[0]["id"] == "MEAL-03", (
        f"Expected MEAL-03 as top-1, got {results[0]['id']!r} "
        f"(score={results[0]['score']:.3f})"
    )


def test_hardware_query_finds_hw_rule(index):
    """'hardware purchase laptop' should surface at least one HW rule in top-3."""
    results = index.search("hardware purchase laptop", top_k=3)
    ids = [r["id"] for r in results]
    assert any(i.startswith("HW") for i in ids), f"Expected HW rule in top-3, got {ids}"


def test_results_have_normalised_score(index):
    """Every returned chunk must carry a score in [0.0, 1.0]."""
    results = index.search("travel reimbursement", top_k=3)
    for r in results:
        assert "score" in r, "Result missing 'score' key"
        assert 0.0 <= r["score"] <= 1.0, f"Score out of range: {r['score']}"


def test_top_k_respected(index):
    """search(top_k=N) returns exactly N results."""
    for k in (1, 3, 5):
        results = index.search("expense", top_k=k)
        assert len(results) == k, f"Expected {k} results, got {len(results)}"


def test_custom_chunks(index):
    """PolicyIndex accepts custom chunks — useful for unit testing without the full policy."""
    mini = [
        {"id": "CUSTOM-01", "text": "No alcohol expenses are reimbursable."},
        {"id": "CUSTOM-02", "text": "Travel must be economy class."},
    ]
    custom_index = PolicyIndex(chunks=mini)
    results = custom_index.search("alcohol bar tab", top_k=1)
    assert results[0]["id"] == "CUSTOM-01"
