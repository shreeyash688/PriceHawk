"""Picks the right scraper for a URL. To support a new website later,
write a new scraper class and add it to SCRAPERS."""
from exceptions import UnsupportedURLError
from scrapers.books_scraper import BooksScraper

SCRAPERS = [BooksScraper()]


def get_scraper(url):
    for scraper in SCRAPERS:
        if scraper.can_handle(url):
            return scraper
    raise UnsupportedURLError("Only books.toscrape.com product pages are supported right now")
