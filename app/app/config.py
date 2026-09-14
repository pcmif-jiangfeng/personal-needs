"""Small, dependency-free runtime configuration for local and hosted use."""
import os
from pathlib import Path

from .db import ROOT


def load_local_env(path=ROOT / ".env"):
    """Load simple KEY=VALUE lines without overriding real environment variables."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key.replace("_", "").isalnum():
            os.environ.setdefault(key, value.strip())


def configured_host():
    return os.environ.get("HOST", "127.0.0.1")


def configured_port():
    try:
        port = int(os.environ.get("PORT", "8765"))
    except ValueError:
        return 8765
    return port if 1 <= port <= 65535 else 8765


def configured_database_path(default):
    value = os.environ.get("DATABASE_PATH")
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path
