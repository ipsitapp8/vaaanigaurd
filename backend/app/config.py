from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Environment-driven settings. Override with VG_* env vars or a .env file."""

    model_config = SettingsConfigDict(env_prefix="VG_", env_file=REPO_ROOT / ".env", extra="ignore")

    data_dir: Path = REPO_ROOT / "data"
    risk_config_path: Path = REPO_ROOT / "config" / "risk.yaml"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Section R: force every ML engine into its deterministic fallback (tests, demo-safe)
    force_fallback: bool = False
    # Section G: +-3 threshold jitter per session; off by default for deterministic demos
    hardened_mode: bool = False

    # Input limits (section E)
    max_audio_bytes: int = 10 * 1024 * 1024
    max_audio_seconds: int = 120

    # Per-engine timeouts in seconds (section R)
    asr_timeout_s: float = 25.0
    engine_timeout_s: float = 8.0

    whisper_model: str = "small"
    audio_retention_hours: int = 24

    @property
    def db_path(self) -> Path:
        return self.data_dir / "vaaniguard.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def load_risk_config() -> dict:
    """Weights, rule thresholds and tier boundaries from config/risk.yaml."""
    with open(get_settings().risk_config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)
