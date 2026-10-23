"""Scraper for eBay websites (ebay.com, ebay.co.uk, ebay.ca, etc.)."""
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from exceptions import PriceNotFoundError, ScraperError, UnsupportedURLError
from scrapers.base_scraper import BaseScraper

EBAY_HOST_RE = re.compile(
    r"^(?:www\.|m\.)?ebay\.(com|co\.uk|ca|com\.au|de|fr|es|it|nl|ie|at|ch|be|pl)$",
    re.IGNORECASE
)

EBAY_PATH_PATTERN = re.compile(r"/itm/(?:[^/]+/)?(\d{9,14})(?:[/?#]|$)", re.IGNORECASE)

DOMAIN_DEFAULT_CURRENCIES = {
    "co.uk": "£",
    "de": "€",
    "fr": "€",
    "es": "€",
    "it": "€",
    "nl": "€",
    "ie": "€",
    "at": "€",
    "ca": "CA$",
    "com.au": "AU$",
    "com": "$",
}


class EbayScraper(BaseScraper):
    retailer_name = "eBay"
    default_currency = "$"

    def _get_tld(self, hostname):
        match = EBAY_HOST_RE.match(hostname or "")
        return match.group(1).lower() if match else "com"

    def can_handle(self, url):
        try:
            parts = urlparse(str(url))
            return parts.scheme in ("http", "https") and bool(parts.hostname and EBAY_HOST_RE.match(parts.hostname))
        except ValueError:
            return False

    def normalize_url(self, url):
        """Validates eBay item URL and returns canonical https://www.ebay.{tld}/itm/{item_id}."""
        try:
            parts = urlparse(str(url).strip())
            port = parts.port
        except ValueError:
            raise UnsupportedURLError("That is not a valid URL")

        if parts.scheme not in ("http", "https"):
            raise UnsupportedURLError("The URL must start with http:// or https://")

        hostname = (parts.hostname or "").lower()
        if not EBAY_HOST_RE.match(hostname) or port is not None or parts.username or parts.password:
            raise UnsupportedURLError("Only standard eBay domains are supported by this scraper")

        tld = self._get_tld(hostname)

        # Match item ID in path
        item_id = None
        match = EBAY_PATH_PATTERN.search(parts.path)
        if match:
            item_id = match.group(1)

        # Fallback to query parameter (e.g. ?item=123456789012)
        if not item_id and parts.query:
            query_dict = parse_qs(parts.query)
            for param in ("item", "id"):
                val = query_dict.get(param, [None])[0]
                if val and val.isdigit() and 9 <= len(val) <= 14:
                    item_id = val
                    break

        if not item_id:
            raise UnsupportedURLError("That is not an eBay product page (missing numeric item ID)")

        return f"https://www.ebay.{tld}/itm/{item_id}"

    def parse(self, html):
        """Extract title, price, currency, and availability from eBay HTML."""
        if not html or not html.strip():
            raise ScraperError("eBay returned an empty response")

        lower_html = html.lower()
        if "security measure" in lower_html or "please verify you are a human" in lower_html:
            raise ScraperError("eBay anti-bot verification or security check detected.")

        soup = BeautifulSoup(html, "html.parser")

        # 1. Try Schema.org JSON-LD first
        json_ld_data = self.extract_from_json_ld(soup)
        if json_ld_data and json_ld_data.get("title") and json_ld_data.get("price") is not None:
            return json_ld_data

        # 2. Extract title via CSS selectors
        title = None
        title_selectors = [
            "h1.x-item-title__mainTitle span",
            "h1.x-item-title__mainTitle",
            "h1#itemTitle",
            "div.vim.d-vi-evo-region h1",
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
            raise PriceNotFoundError("Could not find item title on eBay")

        # Remove "Details about  " prefix if present on legacy eBay templates
        if title.lower().startswith("details about"):
            title = re.sub(r"^details about\s+", "", title, flags=re.IGNORECASE).strip()

        # 3. Extract availability
        available = True
        if (
            "this listing was ended" in lower_html
            or "this listing has ended" in lower_html
            or "out of stock" in lower_html
        ):
            # Check if there is an active buy button
            buy_btn = soup.select_one("#binBtn_btn, a[data-testid='ux-call-to-action']")
            if not buy_btn:
                available = False

        # 4. Extract price
        price = None
        currency = self.default_currency

        price_selectors = [
            "div.x-price-primary span.ux-textspans",
            "span#prcIsum",
            "span#mm-saleDscPrc",
            "div.x-bin-price__content span.ux-textspans",
            "div.x-price-approx__price span.ux-textspans",
            "meta[itemprop='price']",
        ]

        for sel in price_selectors:
            tag = soup.select_one(sel)
            if tag:
                raw_text = tag.get("content") if tag.name == "meta" else tag.get_text(strip=True)
                if raw_text:
                    try:
                        price = self.extract_numeric_price(raw_text)
                        currency = self.extract_currency_symbol(raw_text, self.default_currency)
                        break
                    except PriceNotFoundError:
                        continue

        if price is None:
            if not available:
                raise PriceNotFoundError("eBay item listing has ended or is out of stock with no price")
            raise PriceNotFoundError("Could not find item price on eBay")

        return {
            "title": title,
            "price": price,
            "currency": currency,
            "available": available,
        }
