"""Securely verify real account authentication through FastAPI handlers.

Run after password rotation with:
    ..\\.venv\\Scripts\\python.exe -m scripts.verify_security_credentials

Passwords and bearer tokens stay in process memory and are never printed. The
TestClient is deliberately used without entering its context manager so FastAPI
lifespan startup does not start MQTT or optional background workers.
"""

from __future__ import annotations

import getpass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import User
from app.core.config import DEFAULT_JWT_SECRET_KEY
from app.core.database import SessionLocal
from app.main import app


def _request(
    client: TestClient,
    method: str,
    path: str,
    *,
    body=None,
    token: str | None = None,
):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.request(method, path, json=body, headers=headers)
    try:
        payload = response.json()
    except ValueError:
        payload = None
    return response.status_code, payload


def main() -> int:
    db = SessionLocal()
    try:
        accounts = list(db.scalars(select(User).order_by(User.id.asc())).all())
    finally:
        db.close()
    if not accounts:
        print("AUTHENTICATION_TEST=FAIL (no local accounts found)")
        return 1

    client = TestClient(app)  # Do not use a context manager; skip lifespan startup.
    passed = True

    health_status, _ = _request(client, "GET", "/health")
    health_ok = health_status == 200
    print(f"BACKEND_HEALTH={'PASS' if health_ok else 'FAIL'}")
    passed &= health_ok

    unauthenticated_status, _ = _request(client, "GET", "/api/auth/me")
    protected_ok = unauthenticated_status == 401
    print(f"PROTECTED_API_REQUIRES_TOKEN={'PASS' if protected_ok else 'FAIL'}")
    passed &= protected_ok

    tokens: dict[int, str] = {}
    account_logins_ok = True
    for account in accounts:
        password = getpass.getpass(f"Current password for {account.email}: ")
        status_code, result = _request(
            client,
            "POST",
            "/api/auth/login",
            body={"email": account.email, "password": password},
        )
        del password
        if status_code != 200 or not isinstance(result, dict) or not result.get("access_token"):
            account_logins_ok = False
            continue

        issued_token = result["access_token"]
        profile_status, profile = _request(client, "GET", "/api/auth/me", token=issued_token)
        if profile_status != 200 or not isinstance(profile, dict) or profile.get("id") != account.id:
            account_logins_ok = False
            continue
        tokens[account.id] = issued_token
    all_account_logins_ok = account_logins_ok and len(tokens) == len(accounts)
    print(f"ROTATED_ACCOUNT_LOGIN={'PASS' if all_account_logins_ok else 'FAIL'}")
    passed &= all_account_logins_ok

    retired_password = getpass.getpass("Retired development password to reject (hidden): ")
    old_password_rejected = bool(retired_password)
    for account in accounts:
        status_code, _ = _request(
            client,
            "POST",
            "/api/auth/login",
            body={"email": account.email, "password": retired_password},
        )
        old_password_rejected &= status_code == 401
    del retired_password
    print(f"OLD_DEFAULT_CREDENTIALS_INVALID={'PASS' if old_password_rejected else 'FAIL'}")
    passed &= old_password_rejected

    active_account = next((account for account in accounts if account.is_active), accounts[0])
    old_token = jwt.encode(
        {
            "sub": str(active_account.id),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        DEFAULT_JWT_SECRET_KEY,
        algorithm="HS256",
    )
    old_token_status, _ = _request(client, "GET", "/api/auth/me", token=old_token)
    old_tokens_invalid = old_token_status == 401
    print(f"OLD_JWT_INVALIDATED={'PASS' if old_tokens_invalid else 'FAIL'}")
    passed &= old_tokens_invalid

    admin = next(
        (account for account in accounts if account.role.value == "ADMIN" and account.is_active),
        None,
    )
    non_admin = next(
        (account for account in accounts if account.role.value != "ADMIN" and account.is_active),
        None,
    )
    role_checks_ok = True
    if admin is not None:
        admin_status, _ = _request(client, "GET", "/api/admin/users", token=tokens.get(admin.id))
        role_checks_ok &= admin_status == 200
    if non_admin is not None:
        non_admin_status, _ = _request(
            client,
            "GET",
            "/api/admin/users",
            token=tokens.get(non_admin.id),
        )
        role_checks_ok &= non_admin_status == 403
    print(f"ROLE_AUTHORIZATION={'PASS' if role_checks_ok else 'FAIL'}")
    passed &= role_checks_ok

    print(f"AUTHENTICATION_TEST={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
