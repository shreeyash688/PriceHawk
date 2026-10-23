
"""Shared test helpers: in-memory Supabase mock and fake scraper."""
import unittest
from unittest.mock import patch

from database import db

SAMPLE_PAGE = """
<html><body><div class="col-sm-6 product_main">
  <h1>A Light in the Attic</h1>
  <p class="price_color">£51.77</p>
</div></body></html>
"""
BOOK_URL = "http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
BOOK_URL_2 = "http://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html"


class FakeScraper:
    """Pretends to be a website. Change .price to simulate price changes.
    Prices come back without a currency, i.e. already in the home currency (₹)."""

    retailer_name = "Fake store"

    def __init__(self, price=51.77):
        self.price = price

    def normalize_url(self, url):
        return url.split("?")[0]

    def currency_for_url(self, url):
        return "₹"

    def scrape(self, url):
        return {
            "url": url.split("?")[0],
            "title": "Book " + url[-20:],
            "price": self.price,
        }


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, store, table):
        self.store = store
        self.table_name = table
        self.filters = []
        self.operation = "select"
        self.values = None
        self.sort_column = None
        self.descending = False
        self.start = None
        self.end = None

    def select(self, columns="*"):
        self.operation = "select"
        self.columns = columns
        return self

    def insert(self, values):
        self.operation = "insert"
        self.values = values
        return self

    def update(self, values):
        self.operation = "update"
        self.values = values
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def order(self, column, desc=False):
        self.sort_column = column
        self.descending = desc
        return self

    def limit(self, count):
        self.start = 0
        self.end = count - 1
        return self

    def range(self, start, end):
        self.start = start
        self.end = end
        return self

    def execute(self):
        rows = self.store[self.table_name]


        def matches(row):
            for column, value in self.filters:
                if column.startswith("products."):
                    key = column.split(".", 1)[1]
                    product = next(
                        (
                            p for p in self.store["products"]
                            if p["id"] == row.get("product_id")
                        ),
                        {},
                    )
                    if product.get(key) != value:
                        return False
                elif row.get(column) != value:
                    return False
            return True


        selected = [row for row in rows if matches(row)]

        if self.operation == "insert":
            values_list = self.values if isinstance(self.values, list) else [self.values]
            inserted = []
            for values in values_list:
                row = dict(values)
                if self.table_name == "products":
                    if any(
                        p["url"] == row["url"]
                        and p["notify_email"] == row["notify_email"]
                        for p in self.store["products"]
                    ):
                        from postgrest.exceptions import APIError
                        raise APIError({
                            "message": "duplicate key value violates unique constraint",
                            "code": "23505",
                        })
                    row.update({
                        "id": self.store["next_product_id"],
                        "tracking_active": True,
                        "alert_sent": False,
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "last_checked_at": None,
                        "last_error": None,
                    })
                    self.store["next_product_id"] += 1
                else:
                    row.update({
                        "id": self.store["next_history_id"],
                        "checked_at": "2026-01-01T00:00:00+00:00",
                    })
                    self.store["next_history_id"] += 1
                self.store[self.table_name].append(row)
                inserted.append(row)
            return FakeResponse(inserted)

        if self.operation == "update":
            for row in selected:
                row.update(self.values)
            return FakeResponse(selected)

        if self.operation == "delete":
            for row in selected:
                rows.remove(row)
                if self.table_name == "products":
                    self.store["price_history"][:] = [
                        h for h in self.store["price_history"]
                        if h["product_id"] != row["id"]
                    ]
            return FakeResponse(selected)

        if self.sort_column:
            selected.sort(
                key=lambda row: row.get(self.sort_column, 0),
                reverse=self.descending,
            )

        if self.table_name == "price_history" and "products!inner" in getattr(self, "columns", ""):
            expanded = []
            for history in selected:
                product = next(
                    (p for p in self.store["products"] if p["id"] == history["product_id"]),
                    None,
                )
                if product:
                    expanded.append({
                        **history,
                        "products": {
                            "title": product["title"],
                            "notify_email": product["notify_email"],
                        },
                    })
            selected = expanded

        if self.start is not None:
            selected = selected[self.start:self.end + 1]

        return FakeResponse([dict(row) for row in selected])


class FakeSupabaseClient:
    def __init__(self):
        self.store = {
            "products": [],
            "price_history": [],
            "next_product_id": 1,
            "next_history_id": 1,
        }

    def table(self, table_name):
        return FakeQuery(self.store, table_name)


class DatabaseTestCase(unittest.TestCase):
    """Gives each test an isolated in-memory Supabase mock."""

    def setUp(self):
        self.mock_client = FakeSupabaseClient()
        patcher = patch.object(db, "_client", return_value=self.mock_client)
        patcher.start()
        self.addCleanup(patcher.stop)
