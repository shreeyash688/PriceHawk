"""The brain of PriceHawk: tracking, price checks and alert decisions.

Rules for sending alerts (so the user is never spammed):
  * price <= target and no alert sent yet  -> send ONE email, remember it (alert_sent = 1)
  * price <= target and already sent       -> do nothing
  * price goes back above target           -> alert_sent = 0, so a future drop alerts again
  * email failed                           -> alert_sent stays 0, so we try again next check
"""
import logging
import math
import threading

import config
from database import db
from exceptions import (DemoModeError, DuplicateProductError, PriceHawkError,
                        ScraperError, ValidationError)
from models.product import Product
from scrapers import get_scraper
from services import email_service

logger = logging.getLogger(__name__)

# Only one thread at a time may run the "save price -> decide -> email" step.
# Without this, the background thread and a manual "Check now" could both send an email.
_alert_lock = threading.Lock()


class PriceChecker:
    """Compares a current price with a target price."""

    @staticmethod
    def is_target_reached(current_price, target_price):
        return round(current_price, 2) <= round(target_price, 2)

    @classmethod
    def should_send_alert(cls, current_price, target_price, alert_already_sent):
        return cls.is_target_reached(current_price, target_price) and not alert_already_sent

    @classmethod
    def should_reset_alert(cls, current_price, target_price, alert_already_sent):
        return alert_already_sent and not cls.is_target_reached(current_price, target_price)


# ---------- validation ----------

def _validate_price(value, field_name):
    """Accept a positive, finite number (or numeric text like "12.5"). Return it rounded to 2 decimals."""
    if value is None or isinstance(value, bool):
        raise ValidationError(f"{field_name} must be a number")
    try:
        price = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be a number")
    if not math.isfinite(price) or price <= 0:
        raise ValidationError(f"{field_name} must be greater than 0")
    return round(price, 2)


# ---------- the core step ----------

def _record_price(product_id, price):
    """Save a new price, add it to history, and send an alert if needed."""
    with _alert_lock:
        db.update_price(product_id, price)
        db.add_price_history(product_id, price)
        product = Product.from_row(db.get_product(product_id))

        if PriceChecker.should_send_alert(product.current_price, product.target_price, product.alert_sent):
            if email_service.send_price_alert(product):
                db.set_alert_sent(product_id, True)
        elif PriceChecker.should_reset_alert(product.current_price, product.target_price, product.alert_sent):
            db.set_alert_sent(product_id, False)

        return Product.from_row(db.get_product(product_id))


# ---------- actions used by the API ----------

def preview_product(url):
    """Look up a product WITHOUT saving it (used by the popup to show title and price)."""
    data = get_scraper(url).scrape(url)
    data["already_tracked"] = db.get_product_by_url(data["url"]) is not None
    return data


def track_product(url, target_price):
    target = _validate_price(target_price, "target_price")
    data = get_scraper(url).scrape(url)

    if db.get_product_by_url(data["url"]) is not None:
        raise DuplicateProductError("You are already tracking this product")

    product_id = db.add_product(data["title"], data["url"], data["price"], target)
    logger.info("Now tracking product %s (%s)", product_id, data["title"])
    return _record_price(product_id, data["price"])  # first history entry + instant alert if already cheap


def get_product(product_id):
    return Product.from_row(db.get_product(product_id))


def list_products(sort="newest"):
    # map() turns every database row into a Product object.
    products = list(map(Product.from_row, db.get_all_products()))
    if sort == "deals":
        # lambda = tiny one-use function: closest to (or already below) target comes first
        products.sort(key=lambda product: product.price_gap)
    elif sort != "newest":
        raise ValidationError("sort must be 'newest' or 'deals'")
    return products


def update_product(product_id, data):
    db.get_product(product_id)  # raises "not found" early
    if "target_price" not in data and "tracking_active" not in data:
        raise ValidationError("Send target_price and/or tracking_active")

    if "target_price" in data:
        db.update_target_price(product_id, _validate_price(data["target_price"], "target_price"))
    if "tracking_active" in data:
        if not isinstance(data["tracking_active"], bool):
            raise ValidationError("tracking_active must be true or false")
        db.set_tracking_active(product_id, data["tracking_active"])
    return get_product(product_id)


def delete_product(product_id):
    db.delete_product(product_id)
    logger.info("Deleted product %s", product_id)


def get_history(product_id):
    db.get_product(product_id)  # raises "not found" early
    return [{"price": row["price"], "checked_at": row["checked_at"]}
            for row in db.get_price_history(product_id)]


# ---------- price checks (manual + background) ----------

def check_product(product_id):
    """Scrape one product now and process the new price."""
    product = Product.from_row(db.get_product(product_id))
    try:
        data = get_scraper(product.url).scrape(product.url)
    except ScraperError as error:
        db.record_error(product_id, str(error))
        logger.warning("Check failed for product %s: %s", product_id, error)
        raise
    return _record_price(product_id, data["price"])


def check_all_products():
    """Check every ACTIVE product. One failing product never stops the others."""
    products = map(Product.from_row, db.get_all_products())
    active_products = filter(lambda product: product.tracking_active, products)  # skip paused ones

    checked = 0
    for product in active_products:
        try:
            check_product(product.id)
            checked += 1
        except PriceHawkError as error:
            logger.warning("Skipping product %s this round: %s", product.id, error)
        except Exception:
            logger.exception("Unexpected error while checking product %s", product.id)
    return checked


# ---------- demo mode ----------

def simulate_price(product_id, price):
    """DEMO ONLY: pretend the website now shows this price. Uses the exact same
    logic as a real check, so the alert/dedupe behaviour is genuine."""
    if not config.DEMO_MODE:
        raise DemoModeError("Demo mode is off. Set DEMO_MODE=true in .env")
    new_price = _validate_price(price, "price")
    db.get_product(product_id)  # raises "not found" early
    return _record_price(product_id, new_price)
