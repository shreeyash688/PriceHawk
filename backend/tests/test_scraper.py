import unittest
from unittest.mock import MagicMock, patch

import requests

from exceptions import PriceNotFoundError, ScraperError, UnsupportedURLError
from scrapers import get_scraper
from scrapers.books_scraper import BooksScraper
from tests.helpers import BOOK_URL, SAMPLE_PAGE


class UrlValidationTests(unittest.TestCase):
    def setUp(self):
        self.scraper = BooksScraper()

    def test_valid_url(self):
        self.assertEqual(self.scraper.normalize_url(BOOK_URL), BOOK_URL)

    def test_query_and_fragment_are_removed(self):
        self.assertEqual(self.scraper.normalize_url(BOOK_URL + "?x=1#top"), BOOK_URL)

    def test_bad_urls_are_rejected(self):
        bad_urls = [
            "https://example.com/catalogue/a-light-in-the-attic_1000/index.html",  # wrong site
            "http://books.toscrape.com.evil.com/catalogue/a_1/index.html",         # look-alike host
            "http://localhost:5000/api/products",                                  # internal address
            "ftp://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
            "http://books.toscrape.com/",                                          # not a product page
            "http://books.toscrape.com:8080/catalogue/a-light-in-the-attic_1000/index.html",
            "not a url",
            "",
        ]
        for url in bad_urls:
            with self.subTest(url=url), self.assertRaises(UnsupportedURLError):
                self.scraper.normalize_url(url)

    def test_registry_rejects_unsupported_site(self):
        with self.assertRaises(UnsupportedURLError):
            get_scraper("https://walmart.com/ip/123")


class ParsingTests(unittest.TestCase):
    def test_parse_title_and_price(self):
        self.assertEqual(BooksScraper().parse(SAMPLE_PAGE), ("A Light in the Attic", 51.77))

    def test_missing_price_raises(self):
        with self.assertRaises(PriceNotFoundError):
            BooksScraper().parse("<html><body><h1>Nothing here</h1></body></html>")


class FetchFailureTests(unittest.TestCase):
    def test_timeout(self):
        with patch("scrapers.base_scraper.requests.get", side_effect=requests.Timeout):
            with self.assertRaises(ScraperError):
                BooksScraper().fetch_html(BOOK_URL)

    def test_connection_error(self):
        with patch("scrapers.base_scraper.requests.get", side_effect=requests.ConnectionError("down")):
            with self.assertRaises(ScraperError):
                BooksScraper().fetch_html(BOOK_URL)

    def test_http_404(self):
        response = MagicMock()
        response.raise_for_status.side_effect = requests.HTTPError("404")
        with patch("scrapers.base_scraper.requests.get", return_value=response):
            with self.assertRaises(ScraperError):
                BooksScraper().fetch_html(BOOK_URL)


if __name__ == "__main__":
    unittest.main()
