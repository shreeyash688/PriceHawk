"""BaseScraper: the blueprint every website scraper must follow.

OOP ideas shown here:
  * Abstraction  - abstract methods say WHAT a scraper must do, not HOW.
  * Inheritance  - BooksScraper (and future scrapers) inherit the shared code.
"""
from abc import ABC, abstractmethod

import requests

import config
from exceptions import ScraperError


class BaseScraper(ABC):

    # ----- each website must implement these three -----
    @abstractmethod
    def can_handle(self, url):
        """True if this scraper is meant for this website."""

    @abstractmethod
    def normalize_url(self, url):
        """Check the URL is a valid product page and return a clean version. Raise UnsupportedURLError if not."""

    @abstractmethod
    def parse(self, html):
        """Return (title, price) from the page HTML. Raise PriceNotFoundError if missing."""

    # ----- shared code, inherited by every scraper -----
    def fetch_html(self, url):
        try:
            response = requests.get(
                url,
                timeout=config.REQUEST_TIMEOUT,
                headers={"User-Agent": "PriceHawk/1.0 (student project)"},
            )
            response.raise_for_status()  # turns 404/500 into an exception
        except requests.Timeout:
            raise ScraperError("The website took too long to respond")
        except requests.RequestException as error:
            raise ScraperError(f"Could not load the product page: {error}")
        response.encoding = "utf-8"  # otherwise "£" can come out as "Â£"
        return response.text

    def scrape(self, url):
        """Full job: validate URL -> download page -> read title and price."""
        clean_url = self.normalize_url(url)
        html = self.fetch_html(clean_url)
        title, price = self.parse(html)
        return {"url": clean_url, "title": title, "price": price}
