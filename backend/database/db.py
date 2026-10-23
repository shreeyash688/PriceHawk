
"""Supabase database operations for PriceHawk."""
from datetime import datetime, timezone

from postgrest.exceptions import APIError

from database.supabase_client import get_supabase_client
from exceptions import DuplicateProductError, ProductNotFoundError


def now_iso():
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _client():
    """Return the configured Supabase client."""
    return get_supabase_client()


def _raise_database_error(error):
    """Translate common Supabase/PostgreSQL errors into app exceptions."""
    message = str(error)
    code = getattr(error, "code", None)

    if code == "23505" or "duplicate key" in message.lower():
        raise DuplicateProductError("You're already tracking this product") from error

    raise error


def init_db():
    """Verify that the required Supabase tables are accessible."""
    try:
        _client().table("products").select("id").limit(1).execute()
        _client().table("price_history").select("id").limit(1).execute()
    except APIError as error:
        raise RuntimeError(
            "Could not access the Supabase tables. Run backend/database/schema.sql "
            "in the Supabase SQL Editor, and check SUPABASE_URL / SUPABASE_KEY "
            "in backend/.env."
        ) from error


# ---------- products: Create ----------

def add_product(title, url, price, target_price, notify_email):
    try:
        response = (
            _client()
            .table("products")
            .insert({
                "title": title,
                "url": url,
                "notify_email": notify_email,
                "current_price": price,
                "target_price": target_price,
            })
            .execute()
        )
    except APIError as error:
        _raise_database_error(error)

    if not response.data:
        raise RuntimeError("Supabase did not return the created product.")

    return response.data[0]["id"]


# ---------- products: Read ----------

def get_product(product_id):
    response = (
        _client()
        .table("products")
        .select("*")
        .eq("id", product_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise ProductNotFoundError(f"Product {product_id} not found")
    return response.data[0]


def get_product_by_url_and_email(url, email):
    """Return a product dictionary, or None if not found."""
    response = (
        _client()
        .table("products")
        .select("*")
        .eq("url", url)
        .eq("notify_email", email)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def get_all_products(email=None):
    """Return all products, optionally filtered by email."""
    query = _client().table("products").select("*")
    if email is not None:
        query = query.eq("notify_email", email)
    response = query.order("id", desc=True).execute()
    return response.data or []


def count_products_for_email(email):
    """Count tracked products for an email address."""
    response = (
        _client()
        .table("products")
        .select("id")
        .eq("notify_email", email)
        .execute()
    )
    return len(response.data or [])


# ---------- products: Update ----------

def _update_one_product(values, product_id):
    """Update one product; raise if the product does not exist."""
    response = (
        _client()
        .table("products")
        .update(values)
        .eq("id", product_id)
        .execute()
    )
    if not response.data:
        raise ProductNotFoundError(f"Product {product_id} not found")


def update_target_price(product_id, target_price):
    _update_one_product(
        {"target_price": target_price, "alert_sent": False},
        product_id,
    )


def set_tracking_active(product_id, active):
    _update_one_product({"tracking_active": bool(active)}, product_id)


def update_price(product_id, price):
    """Save a fresh price and clear the last error."""
    _update_one_product(
        {
            "current_price": price,
            "last_checked_at": now_iso(),
            "last_error": None,
        },
        product_id,
    )


def record_error(product_id, message):
    _update_one_product(
        {"last_error": message, "last_checked_at": now_iso()},
        product_id,
    )


def set_alert_sent(product_id, sent):
    _update_one_product({"alert_sent": bool(sent)}, product_id)


# ---------- products: Delete ----------

def delete_product(product_id):
    """Delete a product; Supabase cascades its price history."""
    response = (
        _client()
        .table("products")
        .delete()
        .eq("id", product_id)
        .execute()
    )
    if not response.data:
        raise ProductNotFoundError(f"Product {product_id} not found")


# ---------- price history ----------

def add_price_history(product_id, price):
    response = (
        _client()
        .table("price_history")
        .insert({"product_id": product_id, "price": price})
        .execute()
    )
    return response.data[0] if response.data else None


def get_price_history(product_id):
    response = (
        _client()
        .table("price_history")
        .select("price,checked_at")
        .eq("product_id", product_id)
        .order("id")
        .execute()
    )
    return response.data or []


def iter_price_history(product_id=None, email=None, batch_size=100):
    """Yield history rows in pages for CSV export."""
    offset = 0

    while True:
        query = (
            _client()
            .table("price_history")
            .select("id,product_id,price,checked_at,products!inner(title,notify_email)")
        )

        if product_id is not None:
            query = query.eq("product_id", product_id)
        if email is not None:
            query = query.eq("products.notify_email", email)

        response = (
            query.order("id")
            .range(offset, offset + batch_size - 1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            break

        for row in rows:
            product = row.get("products") or {}
            yield {
                "id": row["id"],
                "product_id": row["product_id"],
                "title": product.get("title"),
                "price": row["price"],
                "checked_at": row["checked_at"],
            }

        if len(rows) < batch_size:
            break
        offset += batch_size
