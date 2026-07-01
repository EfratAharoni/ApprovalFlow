"""
Integration tests — JWT authentication layer.

Tests the auth-service endpoints directly AND the Nginx auth_request guard
on /approvals/{id}/decide.

Requires: docker compose up -d --wait
Run:      pytest tests/integration/test_auth.py -v -m integration
"""
import pytest

from .conftest import GATEWAY_URL

AUTH_URL = GATEWAY_URL  # auth routes exposed through the gateway at /auth/


@pytest.mark.integration
def test_valid_approver_credentials_return_token(http):
    """POST /auth/token with correct approver credentials returns 200 + access_token."""
    resp = http.post(
        f"{AUTH_URL}/auth/token",
        json={"username": "lena", "password": "pass123", "role": "approver"},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "access_token" in body, f"access_token missing from response: {body}"
    assert body.get("token_type") == "bearer"
    assert len(body["access_token"]) > 20, "token looks too short"


@pytest.mark.integration
def test_valid_submitter_credentials_return_token(http):
    """POST /auth/token with correct submitter credentials returns 200 + access_token."""
    resp = http.post(
        f"{AUTH_URL}/auth/token",
        json={"username": "dana", "password": "pass123", "role": "submitter"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.integration
def test_wrong_password_returns_401(http):
    """POST /auth/token with wrong password returns 401."""
    resp = http.post(
        f"{AUTH_URL}/auth/token",
        json={"username": "lena", "password": "wrong", "role": "approver"},
    )
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"


@pytest.mark.integration
def test_decide_without_token_returns_401(http):
    """POST /approvals/{id}/decide without Authorization header returns 401 (Nginx auth_request)."""
    resp = http.post(
        f"{GATEWAY_URL}/approvals/00000000-0000-0000-0000-000000000000/decide",
        json={"action": "APPROVE", "decided_by": "test", "notes": "no token test"},
    )
    assert resp.status_code == 401, (
        f"Expected 401 without token, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.integration
def test_decide_with_approver_token_passes_auth(http):
    """
    POST /approvals/{id}/decide with a valid approver token passes Nginx auth and
    reaches the approval service (which returns 404 for an unknown submission_id —
    that's fine; auth passed).
    """
    # Get approver token
    token_resp = http.post(
        f"{AUTH_URL}/auth/token",
        json={"username": "lena", "password": "pass123", "role": "approver"},
    )
    assert token_resp.status_code == 200
    token = token_resp.json()["access_token"]

    # Hit a non-existent submission — should be 404 from approval-service, NOT 401
    resp = http.post(
        f"{GATEWAY_URL}/approvals/00000000-0000-0000-0000-000000000000/decide",
        json={"action": "APPROVE", "decided_by": "test", "notes": "auth test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Auth passed → upstream reached → 404 or 422 from approval-service (not 401)
    assert resp.status_code != 401, (
        f"Got 401 even with valid approver token — auth_request may be misconfigured"
    )


@pytest.mark.integration
def test_decide_with_submitter_token_returns_403(http):
    """
    POST /approvals/{id}/decide with a submitter token returns 403.
    Nginx auth_request proxies to /auth/verify?required_role=approver, which
    rejects submitter tokens with 403.
    """
    # Get submitter token
    token_resp = http.post(
        f"{AUTH_URL}/auth/token",
        json={"username": "dana", "password": "pass123", "role": "submitter"},
    )
    assert token_resp.status_code == 200
    token = token_resp.json()["access_token"]

    resp = http.post(
        f"{GATEWAY_URL}/approvals/00000000-0000-0000-0000-000000000000/decide",
        json={"action": "APPROVE", "decided_by": "test", "notes": "role test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, (
        f"Expected 403 for submitter token on /decide, got {resp.status_code}: {resp.text}"
    )
