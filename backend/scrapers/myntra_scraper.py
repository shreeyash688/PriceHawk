"""Scraper for Myntra (myntra.com)."""
import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from exceptions import PriceNotFoundError, ScraperError, UnsupportedURLError
from scrapers.base_scraper import BaseScraper

MYNTRA_HOST_RE = re.compile(r"^(?:[a-zA-Z0-9\-]+\.)?myntra\.com$", re.IGNORECASE)
STYLE_ID_RE = re.compile(r"(?:/|^)(\d{5,10})(?:/buy|/?$)", re.IGNORECASE)
SLUG_STYLE_RE = re.compile(r"/([^/]+)/(\d{5,10})(?:/buy|/?$)", re.IGNORECASE)


class MyntraScraper(BaseScraper):
    retailer_name = "Myntra"
    default_currency = "₹"

    def can_handle(self, url):
        try:
            parts = urlparse(str(url))
            return parts.scheme in ("http", "https") and bool(parts.hostname and MYNTRA_HOST_RE.match(parts.hostname))
        except ValueError:
            return False

    def normalize_url(self, url):
        """Validates Myntra URL and returns canonical https://www.myntra.com/{slug}/{style_id}/buy."""
        try:
            parts = urlparse(str(url).strip())
            port = parts.port
        except ValueError:
            raise UnsupportedURLError("That is not a valid URL")

        if parts.scheme not in ("http", "https"):
            raise UnsupportedURLError("The URL must start with http:// or https://")

        hostname = (parts.hostname or "").lower()
        if not MYNTRA_HOST_RE.match(hostname) or port is not None or parts.username or parts.password:
            raise UnsupportedURLError("Only Myntra domains are supported by this scraper")

        path = parts.path.rstrip("/")
        slug_match = SLUG_STYLE_RE.search(path)
        if slug_match:
            slug = slug_match.group(1)
            style_id = slug_match.group(2)
            return f"https://www.myntra.com/{slug}/{style_id}/buy"

        id_match = STYLE_ID_RE.search(path)
        if id_match:
            style_id = id_match.group(1)
            return f"https://www.myntra.com/{style_id}"

        raise UnsupportedURLError("That is not a Myntra product page (missing product style ID)")

    def parse(self, html):
        """Extract title, price, currency, and availability from Myntra HTML."""
        if not html or not html.strip():
            raise ScraperError("Myntra returned an empty response")

        lower_html = html.lower()
        if "access denied" in lower_html or "checking your browser" in lower_html:
            raise ScraperError("Myntra access restriction or verification detected.")

        soup = BeautifulSoup(html, "html.parser")

        # 1. Try to extract from window.__myx script if present
        myx_match = re.search(r"window\.__myx\s*=\s*({.*?});", html)
        if myx_match:
            try:
                myx_data = json.loads(myx_match.group(1))
                pdp = myx_data.get("pdpData", {})
                if pdp:
                    brand = pdp.get("brand", {}).get("name") if isinstance(pdp.get("brand"), dict) else pdp.get("brand")
                    name = pdp.get("name")
                    title = f"{brand} {name}".strip() if brand and name else (name or brand)
                    price_info = pdp.get("price", {})
                    raw_price = price_info.get("discounted") or price_info.get("mrp")
                    if title and raw_price:
                        price = self.extract_numeric_price(str(raw_price))
                        available = not pdp.get("outOfStock", False)
                        return {
                            "title": title,
                            "price": price,
                            "currency": self.default_currency,
                            "available": available,
                        }
            except Exception:
                pass

        # 2. Try Schema.org JSON-LD
        json_ld_data = self.extract_from_json_ld(soup)
        if json_ld_data and json_ld_data.get("title") and json_ld_data.get("price") is not None:
            json_ld_data["currency"] = self.default_currency
            return json_ld_data

        # 3. Extract title via CSS selectors
        brand_tag = soup.select_one("h1.pdp-title")
        name_tag = soup.select_one("h1.pdp-name")

        title = None
        if brand_tag and name_tag:
            title = f"{brand_tag.get_text(strip=True)} {name_tag.get_text(strip=True)}"
        elif name_tag:
            title = name_tag.get_text(strip=True)
        elif brand_tag:
            title = brand_tag.get_text(strip=True)

        if not title:
            og_title = soup.select_one('meta[property="og:title"]')
            if og_title and og_title.get("content"):
                title = og_title["content"].strip()

        if not title:
            raise PriceNotFoundError("Could not find product title on Myntra")

        # 4. Extract availability
        available = True
        if "out of stock" in lower_html or soup.select_one(".pdp-out-of-stock, .size-buttons-outOfStock"):
            # Check if buy button is disabled or missing
            action_btn = soup.select_one(".pdp-add-to-bag")
            if not action_btn or "disabled" in action_btn.get("class", []):
                available = False

        # 5. Extract price
        price = None
        price_selectors = [
            "span.pdp-price strong",
            "span.pdp-price",
            "div.pdp-price-info span.pdp-price",
            "meta[property='product:price:amount']",
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
                raise PriceNotFoundError("Myntra product is currently out of stock and has no price")
            raise PriceNotFoundError("Could not find product price on Myntra")

        return {
            "title": title,
            "price": price,
            "currency": self.default_currency,
            "available": available,
        }
