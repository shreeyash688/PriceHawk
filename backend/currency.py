"""Currencies: detect them in price text and convert prices to the HOME currency (INR by default).

Every price PriceHawk stores, shows and emails is in config.HOME_CURRENCY. A store that
answers in another currency (e.g. Amazon.com in USD) is converted with a live exchange
rate (cached), or with an approximate built-in rate when the rate service is unreachable.
"""
import logging
import threading
import time

import requests

import config

logger = logging.getLogger(__name__)

SYMBOLS = {
    "INR": "₹", "USD": "$", "GBP": "£", "EUR": "€", "CAD": "CA$", "AUD": "AU$", "JPY": "¥",
    "AED": "AED", "SAR": "SAR", "SGD": "S$", "BRL": "R$", "MXN": "MX$", "CHF": "CHF", "PLN": "zł",
}

# Order matters: codes first, then multi-character symbols before the bare "$".
_PATTERNS = [(code, code) for code in SYMBOLS] + [
    ("Rs", "INR"), ("₹", "INR"), ("US$", "USD"), ("CA$", "CAD"), ("C$", "CAD"), ("AU$", "AUD"),
    ("A$", "AUD"), ("S$", "SGD"), ("R$", "BRL"), ("MX$", "MXN"), ("£", "GBP"), ("€", "EUR"),
    ("¥", "JPY"), ("zł", "PLN"), ("$", "USD"),
]

# Approximate rupees per unit: ONLY used when the live rate service can't be reached.
FALLBACK_INR_PER_UNIT = {
    "INR": 1.0, "USD": 86.0, "GBP": 115.0, "EUR": 98.0, "CAD": 62.0, "AUD": 56.0, "JPY": 0.58,
    "AED": 23.4, "SAR": 22.9, "SGD": 66.0, "BRL": 15.5, "MXN": 4.6, "CHF": 106.0, "PLN": 23.0,
}

RATE_URL = "https://api.frankfurter.app/latest"  # free ECB reference rates, no API key
CACHE_SECONDS = 6 * 60 * 60

_cache = {}
_cache_lock = threading.Lock()


def home_code():
    return (config.HOME_CURRENCY or "INR").upper()


def symbol_for(code):
    return SYMBOLS.get((code or "").upper(), code or "")


def home_symbol():
    return symbol_for(home_code())


def to_code(value):
    """'₹' / 'INR 45,999' / 'USD' / '$12' -> ISO code, or None if no currency is recognisable."""
    if not value:
        return None
    text = str(value).strip()
    upper = text.upper()
    if upper in SYMBOLS:
        return upper
    for token, code in _PATTERNS:
        if (token.upper() in upper) if token.isalpha() else (token in text):
            return code
    return None


def _fallback_rate(source, target):
    try:
        return FALLBACK_INR_PER_UNIT[source] / FALLBACK_INR_PER_UNIT[target]
    except KeyError:
        raise ValueError(f"No exchange rate for {source} -> {target}")


def get_rate(source, target):
    """How many `target` units one `source` unit is worth (cached)."""
    source, target = source.upper(), target.upper()
    if source == target:
        return 1.0
    with _cache_lock:
        cached = _cache.get((source, target))
        if cached and time.time() - cached[1] < CACHE_SECONDS:
            return cached[0]

    rate = None
    if config.FX_LIVE_RATES:
        try:
            response = requests.get(RATE_URL, params={"from": source, "to": target}, timeout=5)
            response.raise_for_status()
            rate = float(response.json()["rates"][target])
        except (requests.RequestException, KeyError, ValueError, TypeError) as error:
            logger.warning("Live exchange rate %s->%s unavailable (%s); using built-in rate", source, target, error)
    if rate is None:
        rate = _fallback_rate(source, target)

    with _cache_lock:
        _cache[(source, target)] = (rate, time.time())
    return rate


def to_home(amount, currency):
    """Convert `amount` in `currency` (code or symbol; None = already home) to the home currency."""
    source = to_code(currency) or home_code()
    return round(float(amount) * get_rate(source, home_code()), 2)
