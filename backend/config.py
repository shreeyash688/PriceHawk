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


# Bumped whenever the API changes; the extension warns if it talks to an older backend.
VERSION = "0.4.0"

# --- Server ---
HOST = "127.0.0.1"  # only this computer can reach the API
PORT = int(os.getenv("PORT", "5000"))

# --- Files ---
LOG_FILE = os.getenv("LOG_FILE", os.path.join(BASE_DIR, "pricehawk.log"))

# --- Scraping / monitoring ---
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))  # seconds
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
# After a store blocks us (CAPTCHA), leave that product alone for this long instead of retrying every round.
BLOCKED_RETRY_MINUTES = int(os.getenv("BLOCKED_RETRY_MINUTES", "30"))

# --- Currency: every price is stored, shown and emailed in this currency ---
HOME_CURRENCY = os.getenv("HOME_CURRENCY", "INR").strip().upper() or "INR"
FX_LIVE_RATES = _get_bool("FX_LIVE_RATES", True)  # False = use the built-in approximate rates

# --- Email ---
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# --- Safety / demo ---
MAX_PRODUCTS_PER_EMAIL = int(os.getenv("MAX_PRODUCTS_PER_EMAIL", "20"))  # stops one address being flooded
DEMO_MODE = _get_bool("DEMO_MODE", False)
EXTENSION_ID = os.getenv("EXTENSION_ID", "")

# --- Database (Supabase / PostgreSQL). Use the server-side secret key, never the anon key. ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
