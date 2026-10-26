"""Isolate backend tests from per-user runtime configuration and production IO."""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import shutil
import tempfile
import uuid

from sqlalchemy.engine import URL


_TEST_STATE_ROOT = Path(tempfile.gettempdir()) / f"cityresponder-pytest-{uuid.uuid4().hex}"
_TEST_STATE_ROOT.mkdir(parents=True, exist_ok=False)

# The application must never load the operator's runtime config during pytest.
os.environ["LOCALAPPDATA"] = str(_TEST_STATE_ROOT)
os.environ["CITYRESPONDER_CONFIG_FILE"] = str(_TEST_STATE_ROOT / "runtime-config.env")

# Keep app startup and helpers on in-memory/test-only resources.
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = URL.create(
    "sqlite", database=str(_TEST_STATE_ROOT / "cityresponder-tests.db")
).render_as_string(hide_password=False)
os.environ["JWT_SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["DEV_SEED_PASSWORD"] = secrets.token_urlsafe(24)
os.environ["MQTT_HOST"] = "127.0.0.1"
os.environ["MQTT_PORT"] = "18884"
os.environ["MQTT_USERNAME"] = ""
os.environ["MQTT_PASSWORD"] = ""
os.environ["SENSOR_MQTT_TOPIC_PREFIX"] = "test/city/sensors"
os.environ["SENSOR_ALLOWED_NODE_IDS"] = "SN1"
os.environ["VISION_LIVE_ENABLED"] = "false"
os.environ["VISION_PUBLISH_EVIDENCE_ENABLED"] = "false"
os.environ["VISION_PREVIEW_ENABLED"] = "false"
os.environ["VISION_AI_DISPLAY_ENABLED"] = "false"


def pytest_sessionfinish(session, exitstatus: int) -> None:
    """Remove only the unique temporary per-user state directory created here."""

    shutil.rmtree(_TEST_STATE_ROOT, ignore_errors=True)
