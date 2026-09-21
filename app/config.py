"""Leaf Standard module settings (read from environment / .env)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(BASE_DIR / ".env")

# Same PostgreSQL database as Field Diary (tables are prefixed ls_)
DATABASE_URL = os.getenv("LS_DATABASE_URL", f"sqlite:///{BASE_DIR / 'leaf_standard.db'}")
SECRET_KEY = os.getenv("LS_SECRET_KEY", "change-me")
TOKEN_HOURS = int(os.getenv("LS_TOKEN_HOURS", "720"))  # 30 days - field phones stay logged in
# URL prefix Apache proxies to this service
URL_PREFIX = os.getenv("LS_URL_PREFIX", "/field-diary/leaf-standard").rstrip("/")
# Read-only key for embedding the CEO table in the Fertilizer app
EMBED_KEY = os.getenv("LS_EMBED_KEY", "")
CORS_ORIGINS = [o.strip() for o in os.getenv("LS_CORS_ORIGINS", "").split(",") if o.strip()]
# Colour bands (fraction, 0.70 = 70 %)
TARGET = float(os.getenv("LS_TARGET", "0.70"))
WARN = float(os.getenv("LS_WARN", "0.60"))
# Estate users may edit their own entries for this many days
EDIT_DAYS = int(os.getenv("LS_EDIT_DAYS", "1"))
TIMEZONE = os.getenv("LS_TZ", "Asia/Colombo")

SESSIONS = ["morning", "noon", "evening"]

# Order and grouping exactly as the "Leaf Standard" Excel summary
ESTATES = [
    ("Calsay", "HG"), ("Clarendon", "HG"), ("Dessford", "HG"), ("Somerset", "HG"),
    ("Greatwestern", "HG"), ("Mattakelle", "HG"), ("Palmerston", "HG"), ("Radella", "HG"),
    ("Bearwell", "HG"), ("Holyrood", "HG"), ("Logie", "HG"), ("Wattegoda", "HG"),
    ("Moragalla", "LG"), ("Deniyaya", "LG"), ("Indola", "LG"), ("Kiruwanaganga", "LG"),
]
