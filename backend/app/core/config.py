"""Centralized application settings loaded from environment variables."""

from functools import lru_cache
import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


DEFAULT_JWT_SECRET_KEY = "development-only-change-this-secret"


def runtime_config_file() -> Path:
    """Return the per-user runtime configuration path, outside the project."""

    override = os.environ.get("CITYRESPONDER_CONFIG_FILE")
    if override:
        return Path(override).expanduser().resolve()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "CityResponder" / "config" / ".env"

    config_home = Path(
        os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    ).expanduser()
    return config_home / "CityResponder" / "config" / ".env"


def runtime_data_dir() -> Path:
    """Return a per-user writable data directory outside the project tree."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "CityResponder" / "data"

    data_home = Path(
        os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    ).expanduser()
    return data_home / "CityResponder" / "data"


def _path_is_in_onedrive(path: Path) -> bool:
    """Recognize configured OneDrive roots and conventional OneDrive folders."""

    resolved = path.expanduser().resolve()
    for variable in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        root_value = os.environ.get(variable)
        if root_value:
            try:
                resolved.relative_to(Path(root_value).expanduser().resolve())
                return True
            except ValueError:
                pass
    return any(part.casefold().startswith("onedrive") for part in resolved.parts)


_RUNTIME_CONFIG_FILE = runtime_config_file()
if _path_is_in_onedrive(_RUNTIME_CONFIG_FILE):
    raise RuntimeError(
        "CityResponder runtime configuration must be stored outside OneDrive"
    )


def require_runtime_configuration() -> None:
    """Refuse startup with implicit defaults when external config is absent."""

    if runtime_config_file().is_file():
        return
    required_process_settings = ("ENVIRONMENT", "DATABASE_URL", "JWT_SECRET_KEY")
    if all(os.environ.get(name) for name in required_process_settings):
        return
    raise RuntimeError(
        "CityResponder runtime configuration is missing; refusing database startup"
    )


def _default_database_url() -> str:
    path = runtime_data_dir() / "cityresponder.db"
    return URL.create("sqlite", database=str(path)).render_as_string(
        hide_password=False
    )


class Settings(BaseSettings):
    """Runtime settings for the backend foundation."""

    app_name: str = "CityResponder Backend"
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = 8020
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Additional explicit WebSocket origins for same-origin local gateways.
    # REST CORS remains governed only by cors_allowed_origins.
    websocket_allowed_origins: str = ""
    database_url: str = Field(default_factory=_default_database_url)
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    jwt_secret_key: str = DEFAULT_JWT_SECRET_KEY
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    dev_seed_password: str = ""
    dev_operator_email: str = "operator@example.com"
    dev_firefighter_email: str = "firefighter@example.com"
    dev_risk_planner_email: str = "risk-planner@example.com"
    dev_admin_email: str = "admin@example.com"
    vision_source: str = "CAMERA"
    # A device index is machine-specific. Require local configuration before
    # opening a camera instead of silently selecting the wrong device.
    vision_camera_index: int | None = None
    vision_capture_backend: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "VISION_CAMERA_BACKEND",
            "VISION_CAPTURE_BACKEND",
            "vision_capture_backend",
        ),
    )
    vision_capture_fourcc: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "VISION_CAMERA_FOURCC",
            "VISION_CAPTURE_FOURCC",
            "vision_capture_fourcc",
        ),
    )
    vision_frame_width: int = 1920
    vision_frame_height: int = 1080
    vision_preview_enabled: bool = False
    vision_ai_display_enabled: bool = False
    vision_live_enabled: bool = False
    vision_publish_evidence_enabled: bool = False
    detection_weights: str = (
        "runs/detect/runs/cityresponder_detection_v2/train/weights/best.pt"
    )
    segmentation_weights: str = (
        "runs/segment/runs/cityresponder_segmentation_v1/train2/weights/best.pt"
    )
    vision_inference_size: int = 640
    vision_inference_cpu_threads: int = 2
    vision_inference_device: str = "auto"
    vision_ai_display_target_fps: float = 4.0
    vision_ai_overlay_valid_seconds: float = 1.5
    vision_require_exact_frame_size: bool = True
    vision_display_crop_left: float = 0.0
    vision_display_crop_top: float = 0.0
    vision_display_crop_right: float = 1.0
    vision_display_crop_bottom: float = 1.0
    vision_polygon_roi_enabled: bool = False
    vision_polygon_roi_config_path: str | None = None
    vision_board_crop_coordinates: str = (
        '{"name":"raw_board_crop","x":340,"y":80,"width":1080,"height":840}'
    )
    vision_building_roi_min_width_px: int = 280
    vision_building_roi_min_height_px: int = 180
    vision_min_road_width_px: int = 120
    vision_pixel_to_cm_scale: float | None = None
    sensor_mq2_stale_after_seconds: float = 2.0
    sensor_dht22_stale_after_seconds: float = 3.0
    sensor_digital_stale_after_seconds: float = 2.0
    sensor_allowed_node_ids: str = "SN1"
    sensor_mqtt_topic_prefix: str = "city/sensors"
    vision_stale_after_seconds: float = 1.0
    vision_detection_target_fps: float = 5.0
    vision_segmentation_target_fps: float = 2.0
    vision_building_roi_coordinates: str | None = (
        '{"name":"building_a","x":460,"y":350,"width":340,"height":360}'
    )
    vision_road_roi_coordinates: str | None = (
        '[{"name":"road_main","x":10,"y":675,"width":1035,"height":145}]'
    )
    vision_hazard_roi_coordinates: str | None = None
    vision_road_ir_mapping: str | None = None
    vision_ir_conflict_occupancy_threshold: float | None = None
    vision_ir_conflict_value_threshold: float | None = None
    vision_detection_confidence_threshold: float | None = None
    vision_segmentation_confidence_threshold: float | None = None
    evidence_storage_dir: str = Field(
        default_factory=lambda: str(runtime_data_dir() / "incident_evidence")
    )
    evidence_max_file_size_bytes: int = 10_000_000

    @model_validator(mode="after")
    def require_explicit_public_runtime_security(self) -> "Settings":
        """Reject unsafe fallback credentials and origins outside local dev."""

        if not 1 <= self.vision_inference_cpu_threads <= 16:
            raise ValueError("VISION_INFERENCE_CPU_THREADS must be between 1 and 16")
        if not 0.5 <= self.vision_ai_display_target_fps <= 10.0:
            raise ValueError("VISION_AI_DISPLAY_TARGET_FPS must be between 0.5 and 10")
        if not 0.25 <= self.vision_ai_overlay_valid_seconds <= 5.0:
            raise ValueError("VISION_AI_OVERLAY_VALID_SECONDS must be between 0.25 and 5")
        inference_device = self.vision_inference_device.strip().lower()
        if inference_device not in {"auto", "cpu"} and not (
            inference_device.isdecimal()
            or (
                inference_device.startswith("cuda:")
                and inference_device[5:].isdecimal()
            )
        ):
            raise ValueError(
                "VISION_INFERENCE_DEVICE must be auto, cpu, a device index, or cuda:<index>"
            )

        crop = (
            self.vision_display_crop_left,
            self.vision_display_crop_top,
            self.vision_display_crop_right,
            self.vision_display_crop_bottom,
        )
        if not all(0.0 <= value <= 1.0 for value in crop):
            raise ValueError("VISION_DISPLAY_CROP bounds must be normalized between 0 and 1")
        if crop[0] >= crop[2] or crop[1] >= crop[3]:
            raise ValueError("VISION_DISPLAY_CROP left/top must be before right/bottom")

        if self.vision_ai_display_enabled and (
            self.vision_live_enabled or self.vision_publish_evidence_enabled
        ):
            raise ValueError(
                "Observation-only AI display cannot enable the decision pipeline or evidence publishing"
            )
        if self.vision_ai_display_enabled and not self.vision_preview_enabled:
            raise ValueError("Observation-only AI display requires the shared camera preview")
        if self.vision_preview_enabled and (self.vision_live_enabled or self.vision_publish_evidence_enabled):
            raise ValueError(
                "Camera-only preview requires inference and evidence publishing to remain disabled"
            )

        environment = self.environment.strip().lower()
        if environment in {"development", "dev", "test"}:
            seed_password = self.dev_seed_password.strip()
            if seed_password and (
                len(seed_password) < 16
                or any(marker in seed_password.lower() for marker in ("replace", "change-this"))
            ):
                raise ValueError(
                    "DEV_SEED_PASSWORD must be a private value of at least 16 characters"
                )
            return self

        secret = self.jwt_secret_key.strip()
        if (
            secret == DEFAULT_JWT_SECRET_KEY
            or len(secret) < 43
            or len(set(secret)) < 8
            or any(marker in secret.lower() for marker in ("replace", "change-this", "development-only"))
        ):
            raise ValueError(
                "JWT_SECRET_KEY must be a unique random secret of at least 43 characters outside development"
            )

        seed_password = self.dev_seed_password.strip()
        if len(seed_password) < 16 or any(
            marker in seed_password.lower() for marker in ("replace", "change-this")
        ):
            raise ValueError("DEV_SEED_PASSWORD must be replaced with a strong value outside development")

        origins = [origin.strip().lower() for origin in self.cors_allowed_origins.split(",") if origin.strip()]
        if not origins or any(not origin.startswith("https://") or "*" in origin for origin in origins):
            raise ValueError("CORS_ALLOWED_ORIGINS must contain explicit HTTPS origins outside development")
        if any("localhost" in origin or "127.0.0.1" in origin for origin in origins):
            raise ValueError("CORS_ALLOWED_ORIGINS must not include localhost outside development")

        websocket_origins = [
            origin.strip()
            for origin in self.websocket_allowed_origins.split(",")
            if origin.strip()
        ]
        for origin in websocket_origins:
            parsed = urlsplit(origin)
            hostname = parsed.hostname or ""
            if (
                "*" in origin
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "WEBSOCKET_ALLOWED_ORIGINS must contain exact origins without paths or wildcards"
                )
            if parsed.scheme == "http":
                if origin != "http://127.0.0.1:8080" or hostname != "127.0.0.1":
                    raise ValueError(
                        "HTTP WebSocket origins are limited to the exact loopback demo gateway origin"
                    )
            elif parsed.scheme == "https":
                if not hostname or origin != f"https://{hostname}":
                    raise ValueError(
                        "HTTPS WebSocket origins must be exact canonical host origins"
                    )
            else:
                raise ValueError(
                    "WEBSOCKET_ALLOWED_ORIGINS must use HTTPS, except for the exact loopback demo origin"
                )

        database = make_url(self.database_url)
        if database.get_backend_name() == "sqlite":
            if not database.database or database.database == ":memory:":
                raise ValueError("A file-backed DATABASE_URL is required outside development")
            database_path = Path(database.database)
            if not database_path.is_absolute():
                database_path = (Path.cwd() / database_path).resolve()
            if _path_is_in_onedrive(database_path):
                raise ValueError("SQLite DATABASE_URL must point outside OneDrive")
        return self

    model_config = SettingsConfigDict(
        env_file=_RUNTIME_CONFIG_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""

    return Settings()
