"""Scraper for books.toscrape.com (a practice website made for learning scraping)."""
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from exceptions import PriceNotFoundError, UnsupportedURLError
from scrapers.base_scraper import BaseScraper

ALLOWED_HOST = "books.toscrape.com"
# Matches paths like /catalogue/a-light-in-the-attic_1000/index.html
PRODUCT_PATH = re.compile(r"^/(catalogue/)?[a-z0-9\-]+_\d+/index\.html$")


class BooksScraper(BaseScraper):

    def can_handle(self, url):
        try:
            return urlparse(str(url)).hostname == ALLOWED_HOST
        except ValueError:
            return False

    def normalize_url(self, url):
        """Allow ONLY real product-page URLs on our one trusted host (blocks SSRF)."""
        try:
            parts = urlparse(str(url).strip())
            port = parts.port
        except ValueError:
            raise UnsupportedURLError("That is not a valid URL")

        if parts.scheme not in ("http", "https"):
            raise UnsupportedURLError("The URL must start with http:// or https://")
        if parts.hostname != ALLOWED_HOST or port is not None or parts.username or parts.password:
            raise UnsupportedURLError("Only books.toscrape.com is supported right now")
        if not PRODUCT_PATH.match(parts.path):
            raise UnsupportedURLError("That is not a book product page")

        # Rebuild the URL ourselves: drops ?query and #fragment, so the same
        # book always has exactly one URL in our database.
        return f"{parts.scheme}://{ALLOWED_HOST}{parts.path}"

    def parse(self, html):
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.select_one("div.product_main h1")
        price_tag = soup.select_one("div.product_main p.price_color")
        if title_tag is None or price_tag is None:
            raise PriceNotFoundError("Could not find the title or price on this page")

        match = re.search(r"\d+(?:\.\d+)?", price_tag.get_text())  # "£51.77" -> "51.77"
        if match is None:
            raise PriceNotFoundError("The price on this page is not a number")
        return title_tag.get_text(strip=True), float(match.group())
