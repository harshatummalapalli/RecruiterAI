import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH, override=False)


class Settings(BaseModel):
    """Typed application settings loaded from the environment and .env file."""

    model_config = ConfigDict(extra="ignore")

    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    crustdata_api_key: Optional[str] = Field(default=None, description="CrustData API key")

    @classmethod
    def from_environment(cls, env: Optional[dict[str, str]] = None) -> "Settings":
        source = env if env is not None else os.environ
        raw_values = {
            "openai_api_key": source.get("OPENAI_API_KEY"),
            "crustdata_api_key": source.get("CRUSTDATA_API_KEY"),
        }
        return cls(**raw_values)

    @field_validator("openai_api_key", "crustdata_api_key", mode="before")
    @classmethod
    def _normalize_optional_value(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


_settings: Optional[Settings] = None
_settings_env_signature: Optional[tuple[Optional[str], Optional[str]]] = None


def get_settings() -> Settings:
    """Return the current settings object for the application."""
    global _settings, _settings_env_signature
    env_signature = (
        os.environ.get("OPENAI_API_KEY"),
        os.environ.get("CRUSTDATA_API_KEY"),
    )
    if _settings is None or _settings_env_signature != env_signature:
        _settings = Settings.from_environment()
        _settings_env_signature = env_signature
    return _settings


def get_openai_api_key() -> str | None:
    """Return the configured OpenAI API key from the environment or .env file."""
    return get_settings().openai_api_key


def get_crustdata_api_key() -> str | None:
    """Return the configured CrustData API key from the environment or .env file."""
    return get_settings().crustdata_api_key
