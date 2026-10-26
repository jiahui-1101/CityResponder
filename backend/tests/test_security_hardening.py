from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import authenticate_token
from app.auth.models import User, UserRole
from app.auth.login_rate_limit import LoginRateLimiter
from app.auth.schemas import UserCreate
from app.auth.security import hash_password, verify_password
from app.core.config import Settings
from app.core.config import require_runtime_configuration, runtime_config_file, runtime_data_dir
from app.core.database import _require_existing_production_sqlite
from app.core.database import get_db
from scripts.rotate_user_passwords import create_verified_backup, rotate_accounts


def _memory_sessions():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    User.__table__.create(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def test_non_development_requires_explicit_secret_and_origin():
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret_key="development-only-change-this-secret",
            cors_allowed_origins="https://dashboard.example.com",
        )

    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret_key=secrets.token_urlsafe(48),
            dev_seed_password=secrets.token_urlsafe(24),
            cors_allowed_origins="http://localhost:5173",
        )

    with pytest.raises(ValidationError, match="DEV_SEED_PASSWORD"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret_key=secrets.token_urlsafe(48),
            dev_seed_password="",
            cors_allowed_origins="https://dashboard.example.com",
        )

    Settings(
        _env_file=None,
        environment="production",
        jwt_secret_key=secrets.token_urlsafe(48),
        dev_seed_password=secrets.token_urlsafe(24),
        cors_allowed_origins="https://dashboard.example.com",
    )

    with pytest.raises(ValidationError, match="outside OneDrive"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret_key=secrets.token_urlsafe(48),
            dev_seed_password=secrets.token_urlsafe(24),
            cors_allowed_origins="https://dashboard.example.com",
            database_url=URL.create(
                "sqlite", database=(Path("C:/OneDrive/CityResponder/cityresponder.db")).as_posix()
            ).render_as_string(hide_password=False),
        )


def test_runtime_storage_defaults_are_per_user_and_outside_project(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("CITYRESPONDER_CONFIG_FILE", raising=False)

    assert runtime_config_file() == tmp_path / "CityResponder" / "config" / ".env"
    assert runtime_data_dir() == tmp_path / "CityResponder" / "data"


def test_missing_runtime_config_refuses_implicit_database_startup(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("CITYRESPONDER_CONFIG_FILE", raising=False)
    for name in ("ENVIRONMENT", "DATABASE_URL", "JWT_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="runtime configuration is missing"):
        require_runtime_configuration()


def test_production_sqlite_startup_refuses_missing_or_empty_database(tmp_path):
    missing = tmp_path / "missing.db"
    with pytest.raises(RuntimeError, match="missing or empty"):
        _require_existing_production_sqlite(f"sqlite:///{missing.as_posix()}", "production")
    assert not missing.exists()

    empty = tmp_path / "empty.db"
    empty.touch()
    with pytest.raises(RuntimeError, match="missing or empty"):
        _require_existing_production_sqlite(f"sqlite:///{empty.as_posix()}", "production")


def test_production_sqlite_startup_requires_cityresponder_tables_and_user(tmp_path):
    candidate = tmp_path / "existing.db"
    with sqlite3.connect(candidate) as db:
        db.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY); CREATE TABLE events (id INTEGER PRIMARY KEY);")
    with pytest.raises(RuntimeError, match="no users"):
        _require_existing_production_sqlite(f"sqlite:///{candidate.as_posix()}", "production")

    with sqlite3.connect(candidate) as db:
        db.execute("INSERT INTO users (id) VALUES (1)")
    _require_existing_production_sqlite(f"sqlite:///{candidate.as_posix()}", "production")


def test_development_account_seeding_is_disabled_outside_development(monkeypatch):
    from app.auth import service

    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: type("SettingsStub", (), {"environment": "production"})(),
    )
    monkeypatch.setattr(
        service,
        "SessionLocal",
        lambda: pytest.fail("database must not be opened when seeding is disabled"),
    )
    service.seed_development_users()


def test_development_seeding_requires_a_private_seed_password(monkeypatch):
    from app.auth import service

    class EmptyDatabase:
        def scalar(self, _query):
            return None

        def close(self):
            return None

        def rollback(self):
            return None

        def add_all(self, _users):
            pytest.fail("users must not be added without a private seed password")

    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: type("SettingsStub", (), {"environment": "development", "dev_seed_password": ""})(),
    )
    monkeypatch.setattr(service, "SessionLocal", EmptyDatabase)
    with pytest.raises(RuntimeError, match="private DEV_SEED_PASSWORD"):
        service.seed_development_users()


def test_existing_development_users_do_not_require_seed_password(monkeypatch):
    from app.auth import service

    class ExistingDatabase:
        def scalar(self, _query):
            return 1

        def close(self):
            return None

    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: type("SettingsStub", (), {"environment": "development", "dev_seed_password": ""})(),
    )
    monkeypatch.setattr(service, "SessionLocal", ExistingDatabase)
    service.seed_development_users()


def test_sqlite_backup_is_verified_outside_repository(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="cityresponder-security-test-") as temp:
        root = Path(temp)
        database_path = root / "repo" / "data" / "cityresponder.db"
        database_path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(database_path)) as db:
            db.executescript(
                "CREATE TABLE users (id INTEGER PRIMARY KEY);"
                "CREATE TABLE events (id INTEGER PRIMARY KEY);"
                "INSERT INTO users VALUES (1), (2);"
                "INSERT INTO events VALUES (1), (2), (3);"
            )
            db.commit()
        local_app_data = root / "local-app-data"
        monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

        backup = create_verified_backup(database_path)

        assert backup.is_file()
        assert backup.is_relative_to(local_app_data)
        assert not backup.is_relative_to(database_path.parent)
        with closing(sqlite3.connect(backup)) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
            assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 3


def test_local_security_values_are_custom_and_cors_is_bearer_only():
    from app.core.config import get_settings
    from app.main import app

    settings = get_settings()
    assert settings.jwt_secret_key != "development-only-change-this-secret"
    assert len(settings.jwt_secret_key) >= 43
    assert len(settings.dev_seed_password) >= 16
    cors = next(item for item in app.user_middleware if item.cls.__name__ == "CORSMiddleware")
    assert cors.kwargs["allow_credentials"] is False
    assert "*" not in cors.kwargs["allow_origins"]
    assert "*" not in cors.kwargs["allow_methods"]
    assert "*" not in cors.kwargs["allow_headers"]


def test_websocket_gateway_origin_allowlist_is_exact_and_loopback_scoped():
    Settings(
        _env_file=None,
        environment="production",
        jwt_secret_key=secrets.token_urlsafe(48),
        dev_seed_password=secrets.token_urlsafe(24),
        cors_allowed_origins="https://dashboard.example.com",
        websocket_allowed_origins="http://127.0.0.1:8080,https://demo.example.com",
    )

    for origin in (
        "http://localhost:8080",
        "http://127.0.0.1:8081",
        "http://attacker.example:8080",
        "https://*.example.invalid",
        "https://demo.example.com/path",
    ):
        with pytest.raises(ValidationError, match="WEBSOCKET_ALLOWED_ORIGINS|HTTP WebSocket origins|HTTPS WebSocket origins"):
            Settings(
                _env_file=None,
                environment="production",
                jwt_secret_key=secrets.token_urlsafe(48),
                dev_seed_password=secrets.token_urlsafe(24),
                cors_allowed_origins="https://dashboard.example.com",
                websocket_allowed_origins=origin,
            )


def test_admin_user_creation_rejects_short_passwords():
    with pytest.raises(ValidationError):
        UserCreate(email="new@example.test", password="too-short", role=UserRole.OPERATOR)


def test_rotation_changes_only_password_hashes_for_all_accounts():
    engine, sessions = _memory_sessions()
    with sessions() as db:
        original_password = "Temporary-Old-Password-2026!"
        users = [
            User(
                id=1,
                email="operator@example.test",
                password_hash=hash_password(original_password),
                role=UserRole.OPERATOR,
                is_active=True,
            ),
            User(
                id=2,
                email="admin@example.test",
                password_hash=hash_password(original_password),
                role=UserRole.ADMIN,
                is_active=False,
            ),
        ]
        db.add_all(users)
        db.commit()
        before = [
            (user.id, user.email, user.role, user.is_active, user.created_at)
            for user in db.scalars(select(User).order_by(User.id)).all()
        ]
        old_hashes = {user.id: user.password_hash for user in users}

        supplied = iter(
            [
                "New-Operator-Secret-2026!",
                "New-Operator-Secret-2026!",
                "New-Admin-Secret-2026!",
                "New-Admin-Secret-2026!",
            ]
        )
        rotated = rotate_accounts(
            db,
            confirm=lambda count: count == 2,
            read_secret=lambda _prompt: next(supplied),
            forbidden_passwords=(original_password,),
        )

        after = list(db.scalars(select(User).order_by(User.id)).all())
        assert rotated == ("operator@example.test", "admin@example.test")
        assert [
            (user.id, user.email, user.role, user.is_active, user.created_at)
            for user in after
        ] == before
        assert all(user.password_hash != old_hashes[user.id] for user in after)
        assert verify_password("New-Operator-Secret-2026!", after[0].password_hash)
        assert verify_password("New-Admin-Secret-2026!", after[1].password_hash)
        assert not verify_password(original_password, after[0].password_hash)
    engine.dispose()


@pytest.mark.parametrize(
    "secrets",
    [
        ["new-password-123456", "confirmation-does-not-match"],
        ["short", "short"],
        ["same-password-123456", "same-password-123456", "same-password-123456", "same-password-123456"],
    ],
)
def test_rotation_rejects_invalid_input_without_partial_updates(secrets):
    engine, sessions = _memory_sessions()
    with sessions() as db:
        db.add_all(
            [
                User(email="one@example.test", password_hash=hash_password("prior-password-123456"), role=UserRole.OPERATOR, is_active=True),
                User(email="two@example.test", password_hash=hash_password("prior-password-123456"), role=UserRole.ADMIN, is_active=True),
            ]
        )
        db.commit()
        hashes_before = [user.password_hash for user in db.scalars(select(User).order_by(User.id)).all()]
        provided = iter(secrets)
        with pytest.raises(ValueError):
            rotate_accounts(
                db,
                confirm=lambda _count: True,
                read_secret=lambda _prompt: next(provided),
            )
        hashes_after = [user.password_hash for user in db.scalars(select(User).order_by(User.id)).all()]
        assert hashes_after == hashes_before
    engine.dispose()


def test_old_jwt_secret_no_longer_authenticates():
    from app.auth import dependencies

    engine, sessions = _memory_sessions()
    with sessions() as db:
        user = User(
            email="operator@example.test",
            password_hash=hash_password("Current-Password-2026!"),
            role=UserRole.OPERATOR,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        old_token = jwt.encode(
            {
                "sub": str(user.id),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
            },
            "development-only-change-this-secret",
            algorithm="HS256",
        )
        monkeypatch_settings = dependencies.get_settings
        dependencies.get_settings = lambda: type(
            "SettingsStub", (), {"jwt_secret_key": "N" * 64, "jwt_algorithm": "HS256"}
        )()
        try:
            with pytest.raises(Exception) as error:
                authenticate_token(old_token, db)
            assert getattr(error.value, "status_code", None) == 401
        finally:
            dependencies.get_settings = monkeypatch_settings
    engine.dispose()


def test_login_and_protected_api_work_without_exposing_credentials():
    from app.main import app

    engine, sessions = _memory_sessions()
    account_password = "Rotated-Account-Password-2026!"
    with sessions() as db:
        db.add(
            User(
                email="operator@example.test",
                password_hash=hash_password(account_password),
                role=UserRole.OPERATOR,
                is_active=True,
            )
        )
        db.commit()

    def override_get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        assert client.get("/health").status_code == 200
        assert client.get("/api/auth/me").status_code == 401
        old_login = client.post(
            "/api/auth/login",
            json={"email": "operator@example.test", "password": "known-retired-dev-password-not-valid"},
        )
        assert old_login.status_code == 401
        login = client.post(
            "/api/auth/login",
            json={"email": "operator@example.test", "password": account_password},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        assert client.get("/api/admin/users").status_code == 401
        assert client.get(
            "/api/admin/users", headers={"Authorization": f"Bearer {token}"}
        ).status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def test_login_rate_limit_is_per_account_temporary_bounded_and_resettable():
    now = [100.0]
    limiter = LoginRateLimiter(
        max_attempts=2,
        window_seconds=10,
        max_accounts=2,
        clock=lambda: now[0],
    )

    assert limiter.retry_after("Person@example.test") is None
    limiter.record_failure(" Person@Example.Test ")
    limiter.record_failure("person@example.test")
    assert limiter.retry_after("PERSON@example.test") == 10
    assert limiter.retry_after("another@example.test") is None

    now[0] = 111.0
    assert limiter.retry_after("person@example.test") is None
    limiter.record_failure("person@example.test")
    limiter.reset("PERSON@example.test")
    assert limiter.retry_after("person@example.test") is None

    limiter.record_failure("first@example.test")
    limiter.record_failure("second@example.test")
    limiter.record_failure("third@example.test")
    assert len(limiter._failures) == 2


def test_login_endpoint_returns_retry_after_without_global_lockout(monkeypatch):
    from app.auth import router as auth_router
    from app.main import app

    engine, sessions = _memory_sessions()
    account_password = "Rotated-Account-Password-2026!"
    with sessions() as db:
        db.add(
            User(
                email="operator@example.test",
                password_hash=hash_password(account_password),
                role=UserRole.OPERATOR,
                is_active=True,
            )
        )
        db.commit()

    now = [1_000.0]
    monkeypatch.setattr(
        auth_router,
        "login_rate_limiter",
        LoginRateLimiter(max_attempts=2, window_seconds=10, clock=lambda: now[0]),
    )

    def override_get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        credentials = {"email": "operator@example.test", "password": "wrong-password"}
        assert client.post("/api/auth/login", json=credentials).status_code == 401
        assert client.post("/api/auth/login", json=credentials).status_code == 401
        throttled = client.post("/api/auth/login", json=credentials)
        assert throttled.status_code == 429
        assert throttled.headers["Retry-After"] == "10"

        other = client.post(
            "/api/auth/login",
            json={"email": "different@example.test", "password": "wrong-password"},
        )
        assert other.status_code == 401

        now[0] += 11
        success = client.post(
            "/api/auth/login",
            json={"email": "operator@example.test", "password": account_password},
        )
        assert success.status_code == 200
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
