"""Centralized application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the backend foundation."""

    app_name: str = "CityResponder Backend"
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = 8020
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    database_url: str = "sqlite:///./data/cityresponder.db"
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    jwt_secret_key: str = "development-only-change-this-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    dev_seed_password: str = "CityResponderDev123!"
    dev_operator_email: str = "operator@example.com"
    dev_firefighter_email: str = "firefighter@example.com"
    dev_risk_planner_email: str = "risk-planner@example.com"
    dev_admin_email: str = "admin@example.com"
    vision_source: str = "CAMERA"
    vision_camera_index: int = 1
    vision_frame_width: int = 1920
    vision_frame_height: int = 1080
    detection_weights: str = (
        "runs/detect/runs/cityresponder_detection_v2/train/weights/best.pt"
    )
    segmentation_weights: str = (
        "runs/segment/runs/cityresponder_segmentation_v1/train2/weights/best.pt"
    )
    vision_inference_size: int = 640
    vision_require_exact_frame_size: bool = True
    vision_board_crop_coordinates: str = (
        '{"name":"raw_board_crop","x":340,"y":80,"width":1080,"height":840}'
    )
    vision_building_roi_min_width_px: int = 280
    vision_building_roi_min_height_px: int = 180
    vision_min_road_width_px: int = 120
    vision_pixel_to_cm_scale: float | None = None
    sensor_mq2_stale_after_seconds: float = 2.0
    sensor_dht22_stale_after_seconds: float = 3.0
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
    evidence_storage_dir: str = "./data/incident_evidence"
    evidence_max_file_size_bytes: int = 10_000_000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""

    return Settings()
