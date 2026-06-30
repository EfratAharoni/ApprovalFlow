"""
Unit tests for the RAG policy search module (N5).

5 positive tests: correct rule_id appears in top-3 for representative queries.
1 known-gap test (xfail): documents a semantic-distance limitation — see ADR-008.
"""
import pytest
from app.rag import search_policy


def _top_ids(query: str, top_k: int = 3) -> list[str]:
    return [r["rule_id"] for r in search_policy(query, top_k=top_k)]


def test_meal_per_attendee_rule():
    """Team meal with headcount → MEAL-01 (per-attendee $75 limit)."""
    assert "MEAL-01" in _top_ids("team lunch for 8 employees")


def test_first_class_flight():
    """Business/first-class ticket → TRAVEL-03."""
    assert "TRAVEL-03" in _top_ids("business class flight ticket to London")


def test_saas_subscription():
    """Monthly software subscription → SAAS-01."""
    assert "SAAS-01" in _top_ids("monthly software subscription renewal")


def test_unknown_vendor():
    """Invoice from a vendor never used before → GLOBAL-VENDOR."""
    assert "GLOBAL-VENDOR" in _top_ids("invoice from a vendor we have never worked with before")


def test_math_mismatch():
    """Line items don't reconcile to total → GLOBAL-MATH."""
    assert "GLOBAL-MATH" in _top_ids("line items do not add up to the invoice total amount")


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Known RAG limitation: 'team happy hour beverages' has no lexical overlap with "
        "'Alcohol-only receipts are not reimbursable.' (MEAL-03). "
        "The model ranks MEAL-01 (team meals) higher because 'team' appears in both query "
        "and MEAL-01 text. Note: query='alcohol' DOES find MEAL-03 — but only via keyword "
        "overlap, not true semantics. This test exposes the real gap: informal phrasing "
        "with zero lexical overlap. See ADR-008 for mitigations."
    ),
)
def test_known_gap_alcohol_paraphrase():
    """
    Documents the semantic gap between informal query language and formal policy text.

    WHY 'alcohol' is NOT a good test for this gap:
        query='alcohol' finds MEAL-03 because 'Alcohol' literally appears in the rule text.
        That is keyword matching disguised as semantic search — not a real semantic win.

    WHY 'team happy hour beverages' IS the right test:
        - Zero lexical overlap with 'alcohol-only receipts'
        - 'team' biases the model toward MEAL-01 (team meals, $75/attendee)
        - This is the failure mode that can mislead the LLM into missing MEAL-03

    xfail(strict=False) means:
        - XFAIL: MEAL-03 missing from top-3 → gap confirmed, CI passes
        - XPASS: MEAL-03 found anyway → model surprised us, CI still passes
    """
    rule_ids = _top_ids("team happy hour beverages reimbursement")
    assert "MEAL-03" in rule_ids
