import os
import secrets
from pathlib import Path


SERVICE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICE_DIR.parent
DATABASE_PATH = Path(
    os.environ.get("AUTH_DATABASE_PATH", str(SERVICE_DIR / "auth.db"))
).resolve()
LEGACY_DATABASE_PATH = Path(
    os.environ.get("LEGACY_DATABASE_PATH", str(PROJECT_ROOT / "basedata.db"))
).resolve()
TOKEN_SECRET = os.environ.get("AUTH_TOKEN_SECRET") or secrets.token_urlsafe(48)
TOKEN_MAX_AGE = int(os.environ.get("AUTH_TOKEN_MAX_AGE", "28800"))
