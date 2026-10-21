"""All SQLite code lives here (CRUD = Create, Read, Update, Delete).

Thread safety: every function opens its OWN connection and closes it when
done. The Flask request threads and the background monitor thread therefore
never share a connection.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import config
from exceptions import DuplicateProductError, ProductNotFoundError

SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def now_iso():
    """Current time in UTC as text, e.g. 2026-10-21T09:30:00+00:00"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def get_connection():
    """Open a connection, save (commit) on success, undo (rollback) on error, always close."""
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row  # lets us read columns by name: row["title"]
    conn.execute("PRAGMA foreign_keys = ON")  # needed so ON DELETE CASCADE works
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create the tables if they don't exist yet."""
    with open(SCHEMA_FILE, "r", encoding="utf-8") as schema_file:
        schema = schema_file.read()
    with get_connection() as conn:
        conn.executescript(schema)


# ---------- products: Create ----------

def add_product(title, url, price, target_price):
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO products (title, url, current_price, target_price, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (title, url, price, target_price, now_iso()),
            )
            return cursor.lastrowid
    except sqlite3.IntegrityError as error:
        if "UNIQUE" in str(error):
            raise DuplicateProductError("You are already tracking this product")
        raise


# ---------- products: Read ----------

def get_product(product_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        raise ProductNotFoundError(f"Product {product_id} not found")
    return row


def get_product_by_url(url):
    """Returns the row, or None if we are not tracking this URL."""
    with get_connection() as conn:
        return conn.execute("SELECT * FROM products WHERE url = ?", (url,)).fetchone()


def get_all_products():
    with get_connection() as conn:
        return conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()


# ---------- products: Update ----------

def _update_one_product(sql, params, product_id):
    """Run an UPDATE on one product; raise 'not found' if no row changed."""
    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        if cursor.rowcount == 0:
            raise ProductNotFoundError(f"Product {product_id} not found")


def update_target_price(product_id, target_price):
    # alert_sent goes back to 0: with a new target, an alert is allowed again.
    _update_one_product(
        "UPDATE products SET target_price = ?, alert_sent = 0 WHERE id = ?",
        (target_price, product_id), product_id,
    )


def set_tracking_active(product_id, active):
    _update_one_product(
        "UPDATE products SET tracking_active = ? WHERE id = ?",
        (1 if active else 0, product_id), product_id,
    )


def update_price(product_id, price):
    """Save a fresh price after a successful check (also clears the last error)."""
    _update_one_product(
        "UPDATE products SET current_price = ?, last_checked_at = ?, last_error = NULL WHERE id = ?",
        (price, now_iso(), product_id), product_id,
    )


def record_error(product_id, message):
    _update_one_product(
        "UPDATE products SET last_error = ?, last_checked_at = ? WHERE id = ?",
        (message, now_iso(), product_id), product_id,
    )


def set_alert_sent(product_id, sent):
    _update_one_product(
        "UPDATE products SET alert_sent = ? WHERE id = ?",
        (1 if sent else 0, product_id), product_id,
    )


# ---------- products: Delete ----------

def delete_product(product_id):
    # price_history rows are removed automatically (ON DELETE CASCADE).
    _update_one_product("DELETE FROM products WHERE id = ?", (product_id,), product_id)


# ---------- price history ----------

def add_price_history(product_id, price):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO price_history (product_id, price, checked_at) VALUES (?, ?, ?)",
            (product_id, price, now_iso()),
        )


def get_price_history(product_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT price, checked_at FROM price_history WHERE product_id = ? ORDER BY id",
            (product_id,),
        ).fetchall()


def iter_price_history(product_id=None, batch_size=100):
    """GENERATOR: yields history rows a few at a time instead of loading them all.

    Used by the CSV export so even a huge history uses very little memory.
    """
    sql = (
        "SELECT h.id, h.product_id, p.title, h.price, h.checked_at "
        "FROM price_history h JOIN products p ON p.id = h.product_id"
    )
    params = ()
    if product_id is not None:
        sql += " WHERE h.product_id = ?"
        params = (product_id,)
    sql += " ORDER BY h.id"

    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        while True:
            batch = cursor.fetchmany(batch_size)
            if not batch:
                break
            for row in batch:
                yield row
