"""Scraper for Flipkart (flipkart.com)."""
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from exceptions import PriceNotFoundError, ScraperError, UnsupportedURLError
from scrapers.base_scraper import BaseScraper

FLIPKART_HOST_RE = re.compile(r"^(?:[a-zA-Z0-9\-]+\.)?flipkart\.com$", re.IGNORECASE)
PRODUCT_PATH_RE = re.compile(r"(/[^/?#]+/p/itm[a-zA-Z0-9]+|/p/itm[a-zA-Z0-9]+)", re.IGNORECASE)


class FlipkartScraper(BaseScraper):
    retailer_name = "Flipkart"
    default_currency = "₹"

    def can_handle(self, url):
        try:
            parts = urlparse(str(url))
            return parts.scheme in ("http", "https") and bool(parts.hostname and FLIPKART_HOST_RE.match(parts.hostname))
        except ValueError:
            return False

    def normalize_url(self, url):
        """Validates Flipkart URL and returns canonical https://www.flipkart.com{path}?pid={pid}."""
        try:
            parts = urlparse(str(url).strip())
            port = parts.port
        except ValueError:
            raise UnsupportedURLError("That is not a valid URL")

        if parts.scheme not in ("http", "https"):
            raise UnsupportedURLError("The URL must start with http:// or https://")

        hostname = (parts.hostname or "").lower()
        if not FLIPKART_HOST_RE.match(hostname) or port is not None or parts.username or parts.password:
            raise UnsupportedURLError("Only Flipkart web domains are supported by this scraper")

        path = parts.path
        query_dict = parse_qs(parts.query) if parts.query else {}
        pid = query_dict.get("pid", [None])[0]

        # Match /p/itm... or /{slug}/p/itm...
        match = PRODUCT_PATH_RE.search(path)
        clean_path = match.group(1) if match else None

        if not clean_path and "/p/" in path:
            # Fallback for /slug/p/something
            clean_path = path

        if not clean_path and not pid:
            raise UnsupportedURLError("That is not a Flipkart product page (missing /p/ or product ID)")

        canonical_path = clean_path or "/p/product"
        if pid:
            return f"https://www.flipkart.com{canonical_path}?pid={pid}"
        return f"https://www.flipkart.com{canonical_path}"

    def parse(self, html):
        """Extract title, price, currency, and availability from Flipkart HTML."""
        if not html or not html.strip():
            raise ScraperError("Flipkart returned an empty response")

        lower_html = html.lower()
        if "access denied" in lower_html or "robot or human?" in lower_html:
            raise ScraperError("Flipkart access restriction or verification detected.")

        soup = BeautifulSoup(html, "html.parser")

        # 1. Try Schema.org JSON-LD first
        json_ld_data = self.extract_from_json_ld(soup)
        if json_ld_data and json_ld_data.get("title") and json_ld_data.get("price") is not None:
            json_ld_data["currency"] = self.default_currency
            return json_ld_data

        # 2. Extract title via CSS selectors
        title = None
        title_selectors = [
            "span.B_NuCI",
            "h1._6EBuvT span.VU-ZEz",
            "span.VU-ZEz",
            "h1.yhB1nd span",
            "h1._6EBuvT",
            "h1.yhB1nd",
            "h1",
        ]
        for sel in title_selectors:
            tag = soup.select_one(sel)
            if tag and tag.get_text(strip=True):
                title = tag.get_text(strip=True)
                break

        if not title:
            og_title = soup.select_one('meta[property="og:title"]')
            if og_title and og_title.get("content"):
                title = og_title["content"].strip()

        if not title:
            raise PriceNotFoundError("Could not find product title on Flipkart")

        # 3. Extract availability
        available = True
        out_of_stock_selectors = [
            "div._16FRp0",  # "Sold Out"
            "div._2JC05C",  # "Currently Out of Stock"
            "div.row._38E22e",
        ]
        for sel in out_of_stock_selectors:
            tag = soup.select_one(sel)
            if tag and any(phrase in tag.get_text().lower() for phrase in ["sold out", "out of stock"]):
                available = False
                break

        if "currently out of stock" in lower_html or "this item is currently out of stock" in lower_html:
            available = False

        # 4. Extract price
        price = None
        price_selectors = [
            "div._30jeq3._16Jk6d",
            "div.Nx9bqj.CxhGGd",
            "div._30jeq3",
            "div.Nx9bqj",
            "._30jeq3",
            ".Nx9bqj",
            "div._1vC4OE._3qQ9m1",
            "._1vC4OE",
            "meta[itemprop='price']",
        ]

        for sel in price_selectors:
            tag = soup.select_one(sel)
            if tag:
                raw_text = tag.get("content") if tag.name == "meta" else tag.get_text(strip=True)
                if raw_text:
                    try:
                        price = self.extract_numeric_price(raw_text)
                        break
                    except PriceNotFoundError:
                        continue

        if price is None:
            if not available:
                raise PriceNotFoundError("Flipkart product is currently out of stock and has no price")
            raise PriceNotFoundError("Could not find product price on Flipkart")

        return {
            "title": title,
            "price": price,
            "currency": self.default_currency,
            "available": available,
        }
