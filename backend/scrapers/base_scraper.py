"""BaseScraper: the blueprint every website scraper must follow.

OOP ideas shown here:
  * Abstraction  - abstract methods say WHAT a scraper must do, not HOW.
  * Inheritance  - BooksScraper, AmazonScraper, etc., inherit the shared code.
"""
from abc import ABC, abstractmethod
import math
import re
from urllib.parse import urlparse

import requests

import config
from exceptions import PriceNotFoundError, ScraperError, UnsupportedURLError

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


CURRENCY_MAP = {
    "GBP": "£",
    "USD": "$",
    "INR": "₹",
    "EUR": "€",
    "CAD": "CA$",
    "AUD": "AU$",
    "JPY": "¥",
}


class BaseScraper(ABC):
    """Abstract base class for all retailer scrapers."""

    retailer_name = "Retailer"
    default_currency = "£"

    @abstractmethod
    def can_handle(self, url):
        """True if this scraper is meant for this website."""

    @abstractmethod
    def normalize_url(self, url):
        """Check the URL is a valid product page and return a canonical version."""

    @abstractmethod
    def parse(self, html):
        """Extract product details from HTML.

        Returns a dictionary:
            {"title": str, "price": float, "currency": str, "available": bool}
        or a tuple:
            (title, price) / (title, price, currency, available)
        """

    def get_headers(self, url):
        """Return HTTP headers for fetching the page."""
        return dict(DEFAULT_HEADERS)

    def extract_currency_symbol(self, text_or_code, default=None):
        """Detect or map currency symbol from currency code or price string."""
        if not text_or_code:
            return default or self.default_currency

        text_str = str(text_or_code).strip()
        upper_code = text_str.upper()
        if upper_code in CURRENCY_MAP:
            return CURRENCY_MAP[upper_code]

        for code, sym in CURRENCY_MAP.items():
            if sym in text_str or code in upper_code:
                return sym

        return default or self.default_currency

    def extract_numeric_price(self, text):
        """Parse numeric price from messy currency strings (e.g. '₹1,499.00', '$24.99')."""
        if not text:
            raise PriceNotFoundError("Empty price text")

        cleaned = str(text).replace(",", "").replace("\xa0", " ").strip()
        match = re.search(r"(\d+(?:\.\d{1,2})?)", cleaned)
        if match is None:
            raise PriceNotFoundError(f"Could not parse a numeric price from '{text}'")

        try:
            val = float(match.group(1))
            if not math.isfinite(val) or val <= 0:
                raise PriceNotFoundError("Price must be a positive finite number")
            return round(val, 2)
        except (ValueError, TypeError):
            raise PriceNotFoundError(f"Invalid price value '{text}'")

    def extract_from_json_ld(self, soup):
        """Extract product title, price, currency, and availability from Schema.org JSON-LD if present."""
        import json

        scripts = soup.select('script[type="application/ld+json"]')
        for script in scripts:
            content = script.string or script.get_text()
            if not content:
                continue
            try:
                data = json.loads(content)
            except Exception:
                continue

            # Flatten graphs and arrays
            candidates = []
            if isinstance(data, list):
                candidates.extend(data)
            elif isinstance(data, dict):
                if "@graph" in data and isinstance(data["@graph"], list):
                    candidates.extend(data["@graph"])
                else:
                    candidates.append(data)

            for item in candidates:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("@type")
                is_product = False
                if isinstance(item_type, str) and "product" in item_type.lower():
                    is_product = True
                elif isinstance(item_type, list) and any("product" in str(t).lower() for t in item_type):
                    is_product = True

                if not is_product:
                    continue

                title = item.get("name") or item.get("title")
                offers = item.get("offers")
                offer = None
                if isinstance(offers, dict):
                    if isinstance(offers.get("offers"), list) and offers["offers"]:
                        offer = offers["offers"][0]
                    else:
                        offer = offers
                elif isinstance(offers, list) and offers:
                    offer = offers[0]

                price = None
                currency = self.default_currency
                available = True

                if offer and isinstance(offer, dict):
                    raw_price = offer.get("price") or offer.get("lowPrice")
                    if raw_price is not None:
                        try:
                            price = self.extract_numeric_price(str(raw_price))
                        except PriceNotFoundError:
                            price = None

                    raw_currency = offer.get("priceCurrency")
                    if raw_currency:
                        currency = self.extract_currency_symbol(raw_currency, self.default_currency)

                    avail_str = str(offer.get("availability", "")).lower()
                    if "outofstock" in avail_str or "discontinued" in avail_str or "soldout" in avail_str:
                        available = False
                    elif "instock" in avail_str:
                        available = True

                if title and price is not None:
                    return {
                        "title": str(title).strip(),
                        "price": price,
                        "currency": currency,
                        "available": available,
                    }
        return None

    def fetch_html(self, url):
        """Download page HTML with timeouts and browser headers."""
        try:
            response = requests.get(
                url,
                timeout=config.REQUEST_TIMEOUT,
                headers=self.get_headers(url),
            )
            response.raise_for_status()
        except requests.Timeout:
            raise ScraperError(f"{self.retailer_name} took too long to respond")
        except requests.RequestException as error:
            raise ScraperError(f"Could not load the product page from {self.retailer_name}: {error}")

        # Preserve proper encoding for currency symbols
        if response.encoding is None or response.encoding.lower() in ("iso-8859-1", "ascii"):
            response.encoding = "utf-8"
        return response.text

    def scrape(self, url):
        """Full job: validate URL -> download page -> extract and validate product data."""
        clean_url = self.normalize_url(url)
        html = self.fetch_html(clean_url)
        parsed = self.parse(html)

        if isinstance(parsed, dict):
            title = parsed.get("title")
            price = parsed.get("price")
            currency = parsed.get("currency", self.default_currency)
            available = parsed.get("available", True)
        elif isinstance(parsed, (list, tuple)):
            if len(parsed) >= 4:
                title, price, currency, available = parsed[0], parsed[1], parsed[2], parsed[3]
            elif len(parsed) == 3:
                title, price, currency = parsed[0], parsed[1], parsed[2]
                available = True
            elif len(parsed) == 2:
                title, price = parsed[0], parsed[1]
                currency = self.default_currency
                available = True
            else:
                raise PriceNotFoundError("Scraper parse returned incomplete result")
        else:
            raise PriceNotFoundError("Scraper parse returned invalid data structure")

        if not title or not isinstance(title, str) or not title.strip():
            raise PriceNotFoundError("Could not find a valid product title")

        if price is None or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            raise PriceNotFoundError("Could not find a valid product price")

        return {
            "url": clean_url,
            "title": title.strip(),
            "price": round(float(price), 2),
            "currency": currency or self.default_currency,
            "available": bool(available),
            "retailer": self.retailer_name,
        }
