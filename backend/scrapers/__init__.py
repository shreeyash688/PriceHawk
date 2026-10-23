"""Picks the right scraper for a URL (one scraper class per supported store)."""
from exceptions import UnsupportedURLError
from scrapers.amazon_scraper import AmazonScraper
from scrapers.books_scraper import BooksScraper
from scrapers.ebay_scraper import EbayScraper
from scrapers.flipkart_scraper import FlipkartScraper
from scrapers.myntra_scraper import MyntraScraper

SCRAPERS = [
    BooksScraper(),
    AmazonScraper(),
    FlipkartScraper(),
    EbayScraper(),
    MyntraScraper(),
]

SUPPORTED_STORES = ", ".join(scraper.retailer_name for scraper in SCRAPERS)


def find_scraper(url):
    """Return the scraper for this URL, or None if no store matches."""
    return next((scraper for scraper in SCRAPERS if scraper.can_handle(url)), None)


def get_scraper(url):
    scraper = find_scraper(url)
    if scraper is None:
        raise UnsupportedURLError(f"Supported stores: {SUPPORTED_STORES}")
    return scraper


def currency_for_url(url, default="₹"):
    """Currency symbol of the store a URL belongs to (e.g. amazon.in -> ₹)."""
    scraper = find_scraper(url)
    return scraper.currency_for_url(url) if scraper else default


def retailer_for_url(url):
    scraper = find_scraper(url)
    return scraper.retailer_name if scraper else None
