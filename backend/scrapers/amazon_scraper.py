"""Scraper for Amazon websites (amazon.com, amazon.in, amazon.co.uk, etc.)."""
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from exceptions import PriceNotFoundError, ScraperError, UnsupportedURLError
from scrapers.base_scraper import BaseScraper

AMAZON_HOST_RE = re.compile(
    r"^(?:[a-zA-Z0-9\-]+\.)?amazon\.(?:[a-zA-Z]{2,3}(?:\.[a-zA-Z]{2})?)$",
    re.IGNORECASE
)

ASIN_PATH_PATTERNS = [
    re.compile(r"/(?:dp|gp/product|gp/aw/d|gp/offer-listing|exec/obidos/ASIN|o/ASIN|product|d)(?:/[^/]+)*/([A-Za-z0-9]{10})(?:[/?#]|$)", re.IGNORECASE),
    re.compile(r"/(B0[A-Za-z0-9]{8})(?:[/?#]|$)", re.IGNORECASE),
]

DOMAIN_DEFAULT_CURRENCIES = {
    "in": "₹",
    "co.uk": "£",
    "de": "€",
    "fr": "€",
    "es": "€",
    "it": "€",
    "nl": "€",
    "ca": "CA$",
    "com.au": "AU$",
    "co.jp": "¥",
    "ae": "AED",
    "sa": "SAR",
    "com": "$",
}


class AmazonScraper(BaseScraper):
    retailer_name = "Amazon"
    default_currency = "$"

    def _get_tld(self, hostname):
        clean_host = (hostname or "").lower()
        if "amazon." in clean_host:
            parts = clean_host.split("amazon.", 1)
            if len(parts) > 1 and parts[1]:
                return parts[1]
        return "com"

    def get_headers(self, url):
        headers = super().get_headers(url)
        headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
        })
        return headers

    def can_handle(self, url):
        try:
            parts = urlparse(str(url).strip())
            return parts.scheme in ("http", "https") and bool(parts.hostname and AMAZON_HOST_RE.match(parts.hostname.lower()))
        except ValueError:
            return False

    def normalize_url(self, url):
        """Validates Amazon URL, extracts ASIN, and returns canonical https://www.amazon.{tld}/dp/{ASIN}."""
        try:
            parts = urlparse(str(url).strip())
            port = parts.port
        except ValueError:
            raise UnsupportedURLError("That is not a valid URL")

        if parts.scheme not in ("http", "https"):
            raise UnsupportedURLError("The URL must start with http:// or https://")

        hostname = (parts.hostname or "").lower()
        if not AMAZON_HOST_RE.match(hostname) or port is not None or parts.username or parts.password:
            raise UnsupportedURLError("Only standard Amazon web domains are supported by this scraper")

        tld = self._get_tld(hostname)

        # Look for 10-char ASIN in path
        asin = None
        for pattern in ASIN_PATH_PATTERNS:
            match = pattern.search(parts.path)
            if match:
                asin = match.group(1).upper()
                break

        # If not in path, check query parameters (e.g. ?asin=B08N5WRWNW)
        if not asin and parts.query:
            query_dict = parse_qs(parts.query)
            for param in ("asin", "ASIN"):
                if param in query_dict and len(query_dict[param][0]) == 10:
                    asin = query_dict[param][0].upper()
                    break

        if not asin:
            raise UnsupportedURLError("That is not an Amazon product page (missing 10-character ASIN)")

        # Rebuild canonical URL
        return f"https://www.amazon.{tld}/dp/{asin}"

    def parse(self, html):
        """Extract title, price, currency, and availability from Amazon HTML."""
        if not html or not html.strip():
            raise ScraperError("Amazon returned an empty response")

        # 1. Detect anti-bot challenge / CAPTCHA
        lower_html = html.lower()
        if (
            "type the characters you see in this image" in lower_html
            or "enter the characters you see below" in lower_html
            or "robot check" in lower_html
            or 'id="captchacharacters"' in lower_html
            or "to discuss automated access to amazon data" in lower_html
        ):
            raise ScraperError("Amazon anti-bot verification or CAPTCHA detected. Automated scraping restricted.")

        soup = BeautifulSoup(html, "html.parser")

        # 2. Try Schema.org JSON-LD first
        json_ld_data = self.extract_from_json_ld(soup)
        if json_ld_data and json_ld_data.get("title") and json_ld_data.get("price") is not None:
            return json_ld_data

        # 3. Extract title via CSS selectors
        title = None
        title_selectors = [
            "#productTitle",
            "#title",
            "h1#title",
            "#titleSection h1",
            "span#productTitle",
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
            raise PriceNotFoundError("Could not find product title on Amazon")

        # 4. Extract availability
        available = True
        avail_tag = soup.select_one("#availability, #availability span")
        if avail_tag:
            avail_text = avail_tag.get_text().strip().lower()
            if any(phrase in avail_text for phrase in [
                "currently unavailable",
                "temporarily out of stock",
                "out of stock",
                "we don't know when or if this item will be back",
            ]):
                available = False

        if soup.select_one("#outOfStock"):
            available = False

        # 5. Extract price
        price = None
        currency = self.default_currency

        price_selectors = [
            "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
            "#corePrice_desktop .a-price .a-offscreen",
            "#apex_desktop .a-price .a-offscreen",
            ".priceToPay .a-price .a-offscreen",
            ".priceToPay .a-offscreen",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            "#priceblock_saleprice",
            ".a-price .a-offscreen",
            ".a-offscreen",
            "#price_inside_buybox",
            "#actualPriceValue",
            ".header-price",
        ]

        for sel in price_selectors:
            tag = soup.select_one(sel)
            if tag and tag.get_text(strip=True):
                raw_text = tag.get_text(strip=True)
                try:
                    price = self.extract_numeric_price(raw_text)
                    currency = self.extract_currency_symbol(raw_text, self.default_currency)
                    break
                except PriceNotFoundError:
                    continue

        # If price wasn't found in a single element, check whole + fraction parts
        if price is None:
            whole_tag = soup.select_one(".priceToPay .a-price-whole, .a-price .a-price-whole")
            fraction_tag = soup.select_one(".priceToPay .a-price-fraction, .a-price .a-price-fraction")
            symbol_tag = soup.select_one(".priceToPay .a-price-symbol, .a-price .a-price-symbol")
            if whole_tag:
                whole_str = whole_tag.get_text(strip=True).replace(",", "").replace(".", "")
                fraction_str = fraction_tag.get_text(strip=True) if fraction_tag else "00"
                combined = f"{whole_str}.{fraction_str}"
                try:
                    price = self.extract_numeric_price(combined)
                    if symbol_tag:
                        currency = self.extract_currency_symbol(symbol_tag.get_text(strip=True), self.default_currency)
                except PriceNotFoundError:
                    pass

        if price is None:
            if not available:
                raise PriceNotFoundError("Amazon product is currently unavailable and has no price")
            raise PriceNotFoundError("Could not find product price on Amazon")

        return {
            "title": title,
            "price": price,
            "currency": currency,
            "available": available,
        }
