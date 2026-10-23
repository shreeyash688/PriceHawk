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


def get_scraper(url):
    for scraper in SCRAPERS:
        if scraper.can_handle(url):
            return scraper
    raise UnsupportedURLError(
        "Only supported retailers (Books to Scrape, Amazon, Flipkart, eBay, Myntra) are currently supported"
    )
