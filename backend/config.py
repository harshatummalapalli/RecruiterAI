import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)


def get_openai_api_key() -> str | None:
    """Return the configured OpenAI API key from the environment or .env file."""
    return os.getenv("OPENAI_API_KEY")
