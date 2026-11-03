import os
from pathlib import Path


SERVICE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICE_DIR.parent
DATABASE_PATH = Path(
    os.environ.get("INVENTORY_DATABASE_PATH", str(SERVICE_DIR / "inventory.db"))
).resolve()
LEGACY_DATABASE_PATH = Path(
    os.environ.get("LEGACY_DATABASE_PATH", str(PROJECT_ROOT / "basedata.db"))
).resolve()
AUTH_SERVICE_URL = os.environ.get(
    "AUTH_SERVICE_URL", "http://127.0.0.1:5001"
).rstrip("/")
SERVICE_REQUEST_TIMEOUT = float(os.environ.get("SERVICE_REQUEST_TIMEOUT", "5"))
