"""
Auth Service — JWT token issuing and verification.

POST /auth/token     — issue a JWT for a known user
GET  /auth/verify    — verify Bearer token (called by Nginx auth_request)

Role enforcement:
  Pass ?required_role=approver to reject tokens with role=submitter (HTTP 403).
  Nginx auth_request propagates 403 directly to the caller.
"""
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from pydantic import BaseModel

from .config import settings

app = FastAPI(title="Auth Service", version="1.0.0")


# ── Models ─────────────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    username: str
    password: str
    role: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.post("/auth/token")
def get_token(req: TokenRequest):
    user = settings.users.get(req.username)
    if not user or user["password"] != req.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user["role"] != req.role:
        raise HTTPException(status_code=403, detail=f"Role mismatch: user has role '{user['role']}'")

    exp = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": req.username, "role": req.role, "exp": exp}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer"}


@app.get("/auth/verify")
def verify_token(
    authorization: str = Header(default=None),
    required_role: str = Query(default=None),
):
    """
    Called by Nginx auth_request for protected routes.
    Returns 200 + X-Role/X-Username headers on success.
    Returns 401 if token is missing or invalid.
    Returns 403 if required_role is set and the token's role doesn't qualify.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization[7:]
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {exc}")

    role = payload.get("role", "")
    username = payload.get("sub", "")

    if required_role and role not in (required_role, "admin"):
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions: required '{required_role}', got '{role}'",
        )

    return JSONResponse(
        content={"status": "ok", "username": username, "role": role},
        headers={"X-Username": username, "X-Role": role},
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": "auth-service"}
