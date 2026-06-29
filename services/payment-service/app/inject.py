"""
Runtime failure injection registry — for verification script / integration tests only.
The env-var PAYMENT_FAILURE_INJECT provides a static substring match.
This module adds a dynamic per-submission override settable via internal API endpoints.
"""
from typing import Set

_forced_fail_ids: Set[str] = set()


def register(submission_id: str) -> None:
    _forced_fail_ids.add(submission_id)


def clear(submission_id: str) -> None:
    _forced_fail_ids.discard(submission_id)


def should_force_fail(submission_id: str) -> bool:
    return submission_id in _forced_fail_ids
