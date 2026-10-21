"""Shared test helpers: a temporary database and a fake scraper (no internet needed)."""
import os
import tempfile
import unittest
from unittest.mock import patch

import config
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
    """Pretends to be a website. Change .price to simulate the price moving."""

    def __init__(self, price=51.77):
        self.price = price

    def scrape(self, url):
        return {"url": url.split("?")[0], "title": "Book " + url[-20:], "price": self.price}


class DatabaseTestCase(unittest.TestCase):
    """Gives each test its own empty database file."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        patcher = patch.object(config, "DB_PATH", os.path.join(self._tmp.name, "test.db"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        db.init_db()
