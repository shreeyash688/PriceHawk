"""CSV export using Python's csv module.

Both functions are GENERATORS: they yield one CSV line at a time, and Flask
streams those lines to the browser as they are produced.
"""
import csv
import io

from database import db

PRODUCT_COLUMNS = ["id", "title", "url", "notify_email", "current_price", "target_price",
                   "tracking_active", "created_at", "last_checked_at"]
HISTORY_COLUMNS = ["id", "product_id", "title", "price", "checked_at"]


def _csv_line(values):
    cleaned = []
    for value in values:
        # Stop Excel from running text that starts with = + - @ as a formula
        if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
            value = "'" + value
        cleaned.append(value)
    buffer = io.StringIO()
    csv.writer(buffer).writerow(cleaned)
    return buffer.getvalue()


def products_csv(email):
    yield _csv_line(PRODUCT_COLUMNS)  # header row (so an empty export is still valid)
    for row in db.get_all_products(email):
        yield _csv_line([row[column] for column in PRODUCT_COLUMNS])


def history_csv(email, product_id=None):
    yield _csv_line(HISTORY_COLUMNS)
    for row in db.iter_price_history(product_id, email):
        yield _csv_line(list(row))
