"""Settings. Real environment variables win; the .env file is the fallback for local development."""
import os
from pathlib import Path
from urllib.parse import quote_plus

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def _read_env_file() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    lines = (line for line in ENV_FILE.read_text().splitlines() if "=" in line and not line.startswith("#"))
    return {key.strip(): value.strip() for key, value in (line.split("=", 1) for line in lines)}


def setting(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name) or _read_env_file().get(name) or default


def match_threshold() -> float:
    """Minimum cosine similarity to accept a face as a known employee (chosen from a small webcam test; see the README)."""
    return float(setting("MATCH_THRESHOLD", "0.40"))


def database_url() -> str:
    user, password, name = setting("POSTGRES_USER"), setting("POSTGRES_PASSWORD"), setting("POSTGRES_DB")
    if not (user and password and name):
        raise RuntimeError("POSTGRES_USER, POSTGRES_PASSWORD and POSTGRES_DB must be set (see .env.example)")
    host, port = setting("POSTGRES_HOST", "127.0.0.1"), setting("POSTGRES_PORT", "5433")
    return f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"
