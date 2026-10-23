"""All settings live here.

Values are read from environment variables (or from a local .env file),
so passwords are never written inside the source code.
"""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))  # does nothing if .env is missing


def _get_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


# --- Server ---
HOST = "127.0.0.1"  # only this computer can reach the API
PORT = int(os.getenv("PORT", "5000"))

# --- Files ---
LOG_FILE = os.getenv("LOG_FILE", os.path.join(BASE_DIR, "pricehawk.log"))

# --- Scraping / monitoring ---
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))  # seconds
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
# Currency is not a setting: each store's currency comes from its URL (see scrapers/).

# --- Email ---
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# --- Safety / demo ---
MAX_PRODUCTS_PER_EMAIL = int(os.getenv("MAX_PRODUCTS_PER_EMAIL", "5"))  # stops one address being flooded
DEMO_MODE = _get_bool("DEMO_MODE", False)
EXTENSION_ID = os.getenv("EXTENSION_ID", "")

# --- Database (Supabase / PostgreSQL). Use the server-side secret key, never the anon key. ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
