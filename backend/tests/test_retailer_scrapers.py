"""Automated test suite for all multi-website price tracker scrapers:
Books to Scrape, Amazon, Flipkart, eBay, and Myntra.
"""
import unittest
from unittest.mock import MagicMock, patch

from exceptions import PriceNotFoundError, ScraperError, UnsupportedURLError
from scrapers import (
    SCRAPERS,
    AmazonScraper,
    BooksScraper,
    EbayScraper,
    FlipkartScraper,
    MyntraScraper,
    get_scraper,
)


class ScraperRegistryTests(unittest.TestCase):
    def test_registry_picks_correct_adapter(self):
        cases = [
            ("https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html", BooksScraper),
            ("https://www.amazon.com/dp/B08N5WRWNW", AmazonScraper),
            ("https://www.amazon.in/Apple-iPhone-13/dp/B09G9D8KRQ", AmazonScraper),
            ("https://www.flipkart.com/apple-iphone-13/p/itm6ba123456?pid=MOBG6VF5GXZG9HGF", FlipkartScraper),
            ("https://www.ebay.com/itm/123456789012", EbayScraper),
            ("https://www.ebay.co.uk/itm/123456789012", EbayScraper),
            ("https://www.myntra.com/tshirts/roadster/roadster-shirt/2127874/buy", MyntraScraper),
        ]
        for url, expected_cls in cases:
            with self.subTest(url=url):
                scraper = get_scraper(url)
                self.assertIsInstance(scraper, expected_cls)

    def test_registry_rejects_unsupported_domains(self):
        unsupported = [
            "https://www.walmart.com/ip/123",
            "https://www.target.com/p/item/-/A-123",
            "https://www.bestbuy.com/site/sku/123.p",
            "https://example.com/product",
            "ftp://books.toscrape.com/catalogue/a_1/index.html",
        ]
        for url in unsupported:
            with self.subTest(url=url):
                with self.assertRaises(UnsupportedURLError):
                    get_scraper(url)


class AmazonScraperTests(unittest.TestCase):
    def setUp(self):
        self.scraper = AmazonScraper()

    def test_url_normalization_standard(self):
        url = "https://www.amazon.com/dp/B08N5WRWNW?ref=ppx_yo_dt_b_search_od_title&th=1#customerReviews"
        self.assertEqual(self.scraper.normalize_url(url), "https://www.amazon.com/dp/B08N5WRWNW")

    def test_url_normalization_with_title_slug(self):
        url = "https://www.amazon.in/Apple-iPhone-13-128GB-Starlight/dp/B09G9D8KRQ"
        self.assertEqual(self.scraper.normalize_url(url), "https://www.amazon.in/dp/B09G9D8KRQ")

    def test_url_normalization_gp_product(self):
        url = "https://www.amazon.co.uk/gp/product/B08N5WRWNW/"
        self.assertEqual(self.scraper.normalize_url(url), "https://www.amazon.co.uk/dp/B08N5WRWNW")

    def test_url_normalization_query_asin(self):
        url = "https://www.amazon.com/product-reviews/something?asin=B08N5WRWNW"
        self.assertEqual(self.scraper.normalize_url(url), "https://www.amazon.com/dp/B08N5WRWNW")

    def test_url_normalization_rejects_non_product_pages(self):
        invalid_urls = [
            "https://www.amazon.com/s?k=headphones",
            "https://www.amazon.com/gp/cart/view.html",
            "https://www.amazon.com/b?node=16225007011",
            "https://www.amazon.com/",
            "http://amazon.com.evil.com/dp/B08N5WRWNW",
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(UnsupportedURLError):
                    self.scraper.normalize_url(url)

    def test_parse_standard_html(self):
        html = """
        <html>
            <body>
                <span id="productTitle">Apple iPhone 13 (128GB) - Midnight</span>
                <div id="corePriceDisplay_desktop_feature_div">
                    <span class="a-price a-text-price"><span class="a-offscreen">$699.00</span></span>
                </div>
                <div id="availability">
                    <span class="a-size-medium a-color-success">In Stock</span>
                </div>
            </body>
        </html>
        """
        data = self.scraper.parse(html)
        self.assertEqual(data["title"], "Apple iPhone 13 (128GB) - Midnight")
        self.assertEqual(data["price"], 699.00)
        self.assertEqual(data["currency"], "$")
        self.assertTrue(data["available"])

    def test_parse_deal_price_inr(self):
        html = """
        <html>
            <body>
                <span id="productTitle">Sony WH-1000XM4 Headphones</span>
                <span id="priceblock_dealprice" class="a-color-price">₹22,990.00</span>
                <div id="availability"><span>In stock</span></div>
            </body>
        </html>
        """
        data = self.scraper.parse(html)
        self.assertEqual(data["title"], "Sony WH-1000XM4 Headphones")
        self.assertEqual(data["price"], 22990.00)
        self.assertEqual(data["currency"], "₹")
        self.assertTrue(data["available"])

    def test_parse_split_whole_fraction(self):
        html = """
        <html>
            <body>
                <h1 id="title">Kindle Paperwhite (16 GB)</h1>
                <span class="priceToPay">
                    <span class="a-price-symbol">£</span>
                    <span class="a-price-whole">149<span class="a-price-decimal">.</span></span>
                    <span class="a-price-fraction">99</span>
                </span>
            </body>
        </html>
        """
        data = self.scraper.parse(html)
        self.assertEqual(data["title"], "Kindle Paperwhite (16 GB)")
        self.assertEqual(data["price"], 149.99)
        self.assertEqual(data["currency"], "£")
        self.assertTrue(data["available"])

    def test_parse_json_ld(self):
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Product",
                    "name": "Echo Dot (5th Gen)",
                    "offers": {
                        "@type": "Offer",
                        "price": "49.99",
                        "priceCurrency": "USD",
                        "availability": "https://schema.org/InStock"
                    }
                }
                </script>
            </head>
            <body></body>
        </html>
        """
        data = self.scraper.parse(html)
        self.assertEqual(data["title"], "Echo Dot (5th Gen)")
        self.assertEqual(data["price"], 49.99)
        self.assertEqual(data["currency"], "$")
        self.assertTrue(data["available"])

    def test_parse_out_of_stock_with_price(self):
        html = """
        <html>
            <body>
                <span id="productTitle">Logitech MX Master 3S</span>
                <span id="priceblock_ourprice">$99.99</span>
                <div id="availability">
                    <span>Currently unavailable. We don't know when or if this item will be back in stock.</span>
                </div>
            </body>
        </html>
        """
        data = self.scraper.parse(html)
        self.assertEqual(data["title"], "Logitech MX Master 3S")
        self.assertEqual(data["price"], 99.99)
        self.assertFalse(data["available"])

    def test_parse_out_of_stock_without_price_raises(self):
        html = """
        <html>
            <body>
                <span id="productTitle">Rare Vintage Item</span>
                <div id="availability">
                    <span>Currently unavailable.</span>
                </div>
            </body>
        </html>
        """
        with self.assertRaises(PriceNotFoundError):
            self.scraper.parse(html)

    def test_parse_captcha_challenge_raises_scraper_error(self):
        html = """
        <html>
            <head><title>Robot Check</title></head>
            <body>
                <form action="/errors/validateCaptcha">
                    <h4>Type the characters you see in this image</h4>
                </form>
            </body>
        </html>
        """
        with self.assertRaises(ScraperError) as ctx:
            self.scraper.parse(html)
        self.assertIn("anti-bot", str(ctx.exception).lower())

    def test_parse_missing_title_raises(self):
        html = """<html><body><span class="a-offscreen">$10.00</span></body></html>"""
        with self.assertRaises(PriceNotFoundError):
            self.scraper.parse(html)


class FlipkartScraperTests(unittest.TestCase):
    def setUp(self):
        self.scraper = FlipkartScraper()

    def test_url_normalization_with_pid(self):
        url = "https://www.flipkart.com/apple-iphone-13-starlight-128-gb/p/itm6ba123456?pid=MOBG6VF5GXZG9HGF&lid=LST&marketplace=FLIPKART"
        canonical = self.scraper.normalize_url(url)
        self.assertEqual(canonical, "https://www.flipkart.com/apple-iphone-13-starlight-128-gb/p/itm6ba123456?pid=MOBG6VF5GXZG9HGF")

    def test_url_normalization_without_pid(self):
        url = "https://www.flipkart.com/product/p/itm123456789"
        canonical = self.scraper.normalize_url(url)
        self.assertEqual(canonical, "https://www.flipkart.com/product/p/itm123456789")

    def test_url_normalization_rejects_non_product(self):
        invalid_urls = [
            "https://www.flipkart.com/search?q=mobiles",
            "https://www.flipkart.com/viewcart",
            "https://www.flipkart.com/",
            "http://flipkart.com.attacker.com/p/itm123",
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(UnsupportedURLError):
                    self.scraper.normalize_url(url)

    def test_parse_standard_html(self):
        html = """
        <html>
            <body>
                <span class="B_NuCI">Apple iPhone 13 (Starlight, 128 GB)</span>
                <div class="_30jeq3 _16Jk6d">₹52,999</div>
            </body>
        </html>
        """
        data = self.scraper.parse(html)
        self.assertEqual(data["title"], "Apple iPhone 13 (Starlight, 128 GB)")
        self.assertEqual(data["price"], 52999.00)
        self.assertEqual(data["currency"], "₹")
        self.assertTrue(data["available"])

    def test_parse_alternative_class_selectors(self):
        html = """
        <html>
            <body>
                <h1 class="_6EBuvT"><span class="VU-ZEz">Samsung Galaxy S23 5G</span></h1>
                <div class="Nx9bqj CxhGGd">₹64,999</div>
            </body>
        </html>
        """
        data = self.scraper.parse(html)
        self.assertEqual(data["title"], "Samsung Galaxy S23 5G")
        self.assertEqual(data["price"], 64999.00)
        self.assertEqual(data["currency"], "₹")
        self.assertTrue(data["available"])

    def test_parse_out_of_stock(self):
        html = """
        <html>
            <body>
                <span class="B_NuCI">Google Pixel 7a (Charcoal, 128 GB)</span>
                <div class="_30jeq3">₹37,999</div>
                <div class="_16FRp0">Sold Out</div>
            </body>
        </html>
        """
        data = self.scraper.parse(html)
        self.assertEqual(data["title"], "Google Pixel 7a (Charcoal, 128 GB)")
        self.assertEqual(data["price"], 37999.00)
        self.assertFalse(data["available"])

    def test_parse_access_denied_raises_scraper_error(self):
        html = "<html><head><title>Access Denied</title></head><body>Robot or human?</body></html>"
        with self.assertRaises(ScraperError):
            self.scraper.parse(html)

    def test_parse_missing_price_raises(self):
        html = "<html><body><span class='B_NuCI'>Some Product</span></body></html>"
        with self.assertRaises(PriceNotFoundError):
            self.scraper.parse(html)


class EbayScraperTests(unittest.TestCase):
    def setUp(self):
        self.scraper = EbayScraper()

    def test_url_normalization_standard(self):
        url = "https://www.ebay.com/itm/123456789012?hash=item123&_trkparms=ispr%3D1"
        self.assertEqual(self.scraper.normalize_url(url), "https://www.ebay.com/itm/123456789012")

    def test_url_normalization_with_title_slug(self):
        url = "https://www.ebay.co.uk/itm/Apple-iPhone-13-128GB-Unlocked-/123456789012"
        self.assertEqual(self.scraper.normalize_url(url), "https://www.ebay.co.uk/itm/123456789012")

    def test_url_normalization_query_item(self):
        url = "https://www.ebay.com/itm/viewitem?item=987654321098"
        self.assertEqual(self.scraper.normalize_url(url), "https://www.ebay.com/itm/987654321098")

    def test_url_normalization_rejects_non_product(self):
        invalid_urls = [
            "https://www.ebay.com/sch/i.html?_nkw=shoes",
            "https://www.ebay.com/myb/PurchaseHistory",
            "https://www.ebay.com/",
            "http://ebay.com.fake.com/itm/123456789012",
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(UnsupportedURLError):
                    self.scraper.normalize_url(url)

    def test_parse_standard_html_usd(self):
        html = """
        <html>
            <body>
                <h1 class="x-item-title__mainTitle"><span class="ux-textspans">Sony PlayStation 5 Console</span></h1>
                <div class="x-price-primary"><span class="ux-textspans">US $449.99</span></div>
                <div id="binBtn_btn"><button>Buy It Now</button></div>
            </body>
        </html>
        """
        data = self.scraper.parse(html)
        self.assertEqual(data["title"], "Sony PlayStation 5 Console")
        self.assertEqual(data["price"], 449.99)
        self.assertEqual(data["currency"], "$")
        self.assertTrue(data["available"])

    def test_parse_gbp_price(self):
        html = """
        <html>
            <body>
                <h1 class="x-item-title__mainTitle"><span class="ux-textspans">Dyson V15 Detect Vacuum</span></h1>
                <span id="prcIsum">£549.99</span>
                <div id="binBtn_btn"><button>Buy It Now</button></div>
            </body>
        </html>
        """
        data = self.scraper.parse(html)
        self.assertEqual(data["title"], "Dyson V15 Detect Vacuum")
        self.assertEqual(data["price"], 549.99)
        self.assertEqual(data["currency"], "£")
        self.assertTrue(data["available"])

    def test_parse_ended_listing(self):
        html = """
        <html>
            <body>
                <h1 class="x-item-title__mainTitle"><span class="ux-textspans">Vintage Rolex Submariner</span></h1>
                <div class="x-price-primary"><span class="ux-textspans">$8,500.00</span></div>
                <div>This listing was ended by the seller.</div>
            </body>
        </html>
        """
        data = self.scraper.parse(html)
        self.assertEqual(data["title"], "Vintage Rolex Submariner")
        self.assertEqual(data["price"], 8500.00)
        self.assertFalse(data["available"])

    def test_parse_security_measure_raises(self):
        html = "<html><body>Please verify you are a human. Security Measure</body></html>"
        with self.assertRaises(ScraperError):
            self.scraper.parse(html)

    def test_parse_missing_price_raises(self):
        html = "<html><body><h1 class='x-item-title__mainTitle'><span>Item Without Price</span></h1></body></html>"
        with self.assertRaises(PriceNotFoundError):
            self.scraper.parse(html)


class MyntraScraperTests(unittest.TestCase):
    def setUp(self):
        self.scraper = MyntraScraper()

    def test_url_normalization_with_slug(self):
        url = "https://www.myntra.com/tshirts/roadster/roadster-men-navy-blue-solid-t-shirt/2127874/buy"
        canonical = self.scraper.normalize_url(url)
        self.assertEqual(canonical, "https://www.myntra.com/roadster-men-navy-blue-solid-t-shirt/2127874/buy")

    def test_url_normalization_id_only(self):
        url = "https://www.myntra.com/2127874"
        canonical = self.scraper.normalize_url(url)
        self.assertEqual(canonical, "https://www.myntra.com/2127874")

    def test_url_normalization_rejects_non_product(self):
        invalid_urls = [
            "https://www.myntra.com/men-tshirts",
            "https://www.myntra.com/checkout/cart",
            "https://www.myntra.com/",
            "http://myntra.com.phishing.com/2127874",
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(UnsupportedURLError):
                    self.scraper.normalize_url(url)

    def test_parse_from_window_myx_json(self):
        html = """
        <html>
            <head>
                <script>
                window.__myx = {"pdpData":{"id":2127874,"name":"Men Navy Blue Solid Round Neck T-shirt","brand":{"name":"Roadster"},"price":{"mrp":899,"discounted":399},"outOfStock":false}};
                </script>
            </head>
            <body></body>
        </html>
        """
        data = self.scraper.parse(html)
        self.assertEqual(data["title"], "Roadster Men Navy Blue Solid Round Neck T-shirt")
        self.assertEqual(data["price"], 399.00)
        self.assertEqual(data["currency"], "₹")
        self.assertTrue(data["available"])

    def test_parse_from_css_selectors(self):
        html = """
        <html>
            <body>
                <h1 class="pdp-title">Levis</h1>
                <h1 class="pdp-name">Men 511 Slim Fit Jeans</h1>
                <span class="pdp-price"><strong>₹1,999</strong></span>
                <button class="pdp-add-to-bag">Add to Bag</button>
            </body>
        </html>
        """
        data = self.scraper.parse(html)
        self.assertEqual(data["title"], "Levis Men 511 Slim Fit Jeans")
        self.assertEqual(data["price"], 1999.00)
        self.assertEqual(data["currency"], "₹")
        self.assertTrue(data["available"])

    def test_parse_out_of_stock(self):
        html = """
        <html>
            <body>
                <h1 class="pdp-title">Nike</h1>
                <h1 class="pdp-name">Air Force 1 '07 Sneakers</h1>
                <span class="pdp-price">₹8,195</span>
                <div class="pdp-out-of-stock">Out of stock</div>
            </body>
        </html>
        """
        data = self.scraper.parse(html)
        self.assertEqual(data["title"], "Nike Air Force 1 '07 Sneakers")
        self.assertEqual(data["price"], 8195.00)
        self.assertFalse(data["available"])

    def test_parse_access_restriction_raises(self):
        html = "<html><body>Access Denied - Checking your browser</body></html>"
        with self.assertRaises(ScraperError):
            self.scraper.parse(html)

    def test_parse_missing_price_raises(self):
        html = "<html><body><h1 class='pdp-name'>Shirt Without Price</h1></body></html>"
        with self.assertRaises(PriceNotFoundError):
            self.scraper.parse(html)


class EndToEndScrapeMethodTests(unittest.TestCase):
    def test_amazon_scrape_returns_full_contract(self):
        scraper = AmazonScraper()
        mock_html = """
        <html>
            <body>
                <span id="productTitle">MacBook Air M2</span>
                <span class="priceToPay"><span class="a-offscreen">$999.00</span></span>
                <div id="availability"><span>In Stock</span></div>
            </body>
        </html>
        """
        with patch.object(scraper, "fetch_html", return_value=mock_html):
            result = scraper.scrape("https://www.amazon.com/dp/B0B3C57X27?ref=xyz")
            self.assertEqual(result["url"], "https://www.amazon.com/dp/B0B3C57X27")
            self.assertEqual(result["title"], "MacBook Air M2")
            self.assertEqual(result["price"], 999.00)
            self.assertEqual(result["currency"], "$")
            self.assertTrue(result["available"])
            self.assertEqual(result["retailer"], "Amazon")

    def test_flipkart_scrape_returns_full_contract(self):
        scraper = FlipkartScraper()
        mock_html = """
        <html>
            <body>
                <span class="B_NuCI">Apple iPhone 15 (Blue, 128 GB)</span>
                <div class="_30jeq3 _16Jk6d">₹65,999</div>
            </body>
        </html>
        """
        with patch.object(scraper, "fetch_html", return_value=mock_html):
            result = scraper.scrape("https://www.flipkart.com/apple-iphone-15/p/itm123456?pid=MOBG123456789")
            self.assertEqual(result["url"], "https://www.flipkart.com/apple-iphone-15/p/itm123456?pid=MOBG123456789")
            self.assertEqual(result["title"], "Apple iPhone 15 (Blue, 128 GB)")
            self.assertEqual(result["price"], 65999.00)
            self.assertEqual(result["currency"], "₹")
            self.assertTrue(result["available"])
            self.assertEqual(result["retailer"], "Flipkart")

    def test_ebay_scrape_returns_full_contract(self):
        scraper = EbayScraper()
        mock_html = """
        <html>
            <body>
                <h1 class="x-item-title__mainTitle"><span class="ux-textspans">Nintendo Switch OLED</span></h1>
                <div class="x-price-primary"><span class="ux-textspans">US $299.99</span></div>
            </body>
        </html>
        """
        with patch.object(scraper, "fetch_html", return_value=mock_html):
            result = scraper.scrape("https://www.ebay.com/itm/123456789012?var=1")
            self.assertEqual(result["url"], "https://www.ebay.com/itm/123456789012")
            self.assertEqual(result["title"], "Nintendo Switch OLED")
            self.assertEqual(result["price"], 299.99)
            self.assertEqual(result["currency"], "$")
            self.assertTrue(result["available"])
            self.assertEqual(result["retailer"], "eBay")

    def test_myntra_scrape_returns_full_contract(self):
        scraper = MyntraScraper()
        mock_html = """
        <html>
            <body>
                <h1 class="pdp-title">Puma</h1>
                <h1 class="pdp-name">Men Running Shoes</h1>
                <span class="pdp-price"><strong>₹3,499</strong></span>
            </body>
        </html>
        """
        with patch.object(scraper, "fetch_html", return_value=mock_html):
            result = scraper.scrape("https://www.myntra.com/shoes/puma/puma-shoes/2127874/buy")
            self.assertEqual(result["url"], "https://www.myntra.com/puma-shoes/2127874/buy")
            self.assertEqual(result["title"], "Puma Men Running Shoes")
            self.assertEqual(result["price"], 3499.00)
            self.assertEqual(result["currency"], "₹")
            self.assertTrue(result["available"])
            self.assertEqual(result["retailer"], "Myntra")

    def test_books_scrape_returns_full_contract(self):
        scraper = BooksScraper()
        mock_html = """
        <html>
            <body>
                <div class="product_main">
                    <h1>Soumission</h1>
                    <p class="price_color">£50.10</p>
                    <p class="instock availability">In stock (20 available)</p>
                </div>
            </body>
        </html>
        """
        with patch.object(scraper, "fetch_html", return_value=mock_html):
            result = scraper.scrape("https://books.toscrape.com/catalogue/soumission_998/index.html")
            self.assertEqual(result["url"], "https://books.toscrape.com/catalogue/soumission_998/index.html")
            self.assertEqual(result["title"], "Soumission")
            self.assertEqual(result["price"], 50.10)
            self.assertEqual(result["currency"], "£")
            self.assertTrue(result["available"])
            self.assertEqual(result["retailer"], "Books to Scrape")


class MultiRetailerApiIntegrationTests(unittest.TestCase):
    def setUp(self):
        import app as app_module
        from tests.helpers import DatabaseTestCase
        # Set up a test DB instance
        self.db_helper = DatabaseTestCase()
        self.db_helper.setUp()
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.db_helper.tearDown()

    def test_api_preview_multi_retailer(self):
        mock_html = """
        <html>
            <body>
                <span class="B_NuCI">Flipkart Test Product</span>
                <div class="_30jeq3">₹1,299</div>
            </body>
        </html>
        """
        with patch("scrapers.base_scraper.BaseScraper.fetch_html", return_value=mock_html):
            res = self.client.post("/api/preview", json={
                "url": "https://www.flipkart.com/p/itm123456?pid=TESTPID12345678",
                "email": "shopper@domain.com"
            })
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["title"], "Flipkart Test Product")
            self.assertEqual(data["price"], 1299.00)
            self.assertEqual(data["currency"], "₹")
            self.assertFalse(data["already_tracked"])

    def test_api_track_and_check_multi_retailer(self):
        mock_html = """
        <html>
            <body>
                <h1 class="x-item-title__mainTitle"><span class="ux-textspans">eBay Track Item</span></h1>
                <div class="x-price-primary"><span class="ux-textspans">$150.00</span></div>
            </body>
        </html>
        """
        with patch("scrapers.base_scraper.BaseScraper.fetch_html", return_value=mock_html), \
             patch("services.email_service.send_price_alert", return_value=True) as mock_email:

            # 1. Track the eBay product (target is in rupees; $1 = ₹86 with the test rates)
            track_res = self.client.post("/api/products", json={
                "url": "https://www.ebay.com/itm/987654321098",
                "target_price": 10000.00,
                "email": "ebaybuyer@example.com"
            })
            self.assertEqual(track_res.status_code, 201)
            prod = track_res.get_json()
            prod_id = prod["id"]
            self.assertEqual(prod["current_price"], 12900.00)  # $150 -> ₹12,900
            self.assertEqual(prod["currency"], "₹")
            self.assertEqual(prod["target_price"], 10000.00)

            # Price is ₹12,900, target is ₹10,000 -> no email yet
            self.assertFalse(mock_email.called)

            # 2. Price drops to $90 (below target $100) -> check product
            dropped_html = """
            <html>
                <body>
                    <h1 class="x-item-title__mainTitle"><span class="ux-textspans">eBay Track Item</span></h1>
                    <div class="x-price-primary"><span class="ux-textspans">$90.00</span></div>
                </body>
            </html>
            """
            with patch("scrapers.base_scraper.BaseScraper.fetch_html", return_value=dropped_html):
                check_res = self.client.post(f"/api/products/{prod_id}/check")
                self.assertEqual(check_res.status_code, 200)
                checked = check_res.get_json()
                self.assertEqual(checked["current_price"], 7740.00)  # $90 -> ₹7,740
                self.assertTrue(checked["alert_sent"])
                # Email alert was triggered!
                self.assertTrue(mock_email.called)


class RegressionBooksOnlyErrorTests(unittest.TestCase):
    """Proves that valid supported retailers never produce the old Books-only error."""

    def setUp(self):
        import app as app_module
        from tests.helpers import DatabaseTestCase
        self.db_helper = DatabaseTestCase()
        self.db_helper.setUp()
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.db_helper.tearDown()

    def test_supported_retailers_never_return_books_only_error_on_preview(self):
        retailer_urls = [
            ("https://www.amazon.com/dp/B08N5WRWNW", "Amazon"),
            ("https://www.amazon.in/dp/B09G9D8KRQ", "Amazon"),
            ("https://www.flipkart.com/product/p/itm123456?pid=MOB123456789012", "Flipkart"),
            ("https://www.ebay.com/itm/123456789012", "eBay"),
            ("https://www.myntra.com/tshirt/brand/item/2127874/buy", "Myntra"),
            ("https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html", "Books to Scrape"),
        ]
        mock_html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Product",
                    "name": "Universal Product",
                    "offers": {
                        "@type": "Offer",
                        "price": "49.99",
                        "priceCurrency": "USD",
                        "availability": "https://schema.org/InStock"
                    }
                }
                </script>
            </head>
            <body>
                <div class="product_main">
                    <h1>Universal Product</h1>
                    <p class="price_color">£49.99</p>
                </div>
            </body>
        </html>
        """
        for url, retailer in retailer_urls:
            with self.subTest(retailer=retailer, url=url):
                with patch("scrapers.base_scraper.BaseScraper.fetch_html", return_value=mock_html):
                    res = self.client.post("/api/preview", json={"url": url})
                    self.assertEqual(res.status_code, 200, f"Failed for {retailer}: {res.get_data(as_text=True)}")
                    body = res.get_json()
                    self.assertNotIn("Only books.toscrape.com", str(body))
                    self.assertIn("price", body)

    def test_supported_retailers_never_return_books_only_error_on_track(self):
        amazon_url = "https://www.amazon.com/dp/B08N5WRWNW"
        mock_html = """
        <html>
            <body>
                <span id="productTitle">Amazon Laptop</span>
                <span class="a-offscreen">$999.00</span>
            </body>
        </html>
        """
        with patch("scrapers.base_scraper.BaseScraper.fetch_html", return_value=mock_html):
            res = self.client.post("/api/products", json={
                "url": amazon_url,
                "target_price": 800.00,
                "email": "user@example.com"
            })
            self.assertEqual(res.status_code, 201)
            body = res.get_json()
            self.assertNotIn("Only books.toscrape.com", str(body))
            self.assertEqual(body["current_price"], 85914.00)  # $999 converted to rupees
            self.assertEqual(body["currency"], "₹")

    def test_unsupported_error_message_lists_all_supported_retailers(self):
        res = self.client.post("/api/preview", json={"url": "https://unsupported-shop.xyz/p/123"})
        self.assertEqual(res.status_code, 400)
        error_msg = res.get_json().get("error", "")
        self.assertNotIn("Only books.toscrape.com product pages are supported right now", error_msg)
        self.assertIn("Books to Scrape", error_msg)
        self.assertIn("Amazon", error_msg)
        self.assertIn("Flipkart", error_msg)
        self.assertIn("eBay", error_msg)
        self.assertIn("Myntra", error_msg)



class CurrencyTests(unittest.TestCase):
    """Currency comes from the store/domain, so emails and the popup always agree."""

    def test_currency_per_store(self):
        from scrapers import currency_for_url
        cases = [
            ("https://www.amazon.in/dp/B09G9D8KRQ", "₹"),
            ("https://www.flipkart.com/x/p/itm123", "₹"),
            ("https://www.myntra.com/shirts/x/12345678/buy", "₹"),
            ("https://www.amazon.com/dp/B08N5WRWNW", "$"),
            ("https://www.amazon.co.uk/dp/B08N5WRWNW", "£"),
            ("https://www.amazon.de/dp/B08N5WRWNW", "€"),
            ("https://www.ebay.co.uk/itm/123456789012", "£"),
            ("http://books.toscrape.com/catalogue/a_1/index.html", "£"),
        ]
        for url, symbol in cases:
            with self.subTest(url=url):
                self.assertEqual(currency_for_url(url), symbol)

    def test_amazon_in_scrape_is_rupees_even_without_symbol_in_page(self):
        html = """<html><span id="productTitle">Mouse</span>
                  <span class="a-price"><span class="a-offscreen">370.00</span></span></html>"""
        scraper = AmazonScraper()
        with patch.object(scraper, "fetch_html", return_value=html):
            self.assertEqual(scraper.scrape("https://www.amazon.in/dp/B0DXNT1234")["currency"], "₹")

    def test_unknown_amazon_lookalike_domains_rejected(self):
        for url in ("https://www.amazon.xyz/dp/B08N5WRWNW", "https://evil.amazon.zz/dp/B08N5WRWNW",
                    "https://shop.amazon.in.evil.com/dp/B08N5WRWNW"):
            with self.subTest(url=url):
                self.assertFalse(AmazonScraper().can_handle(url))
                with self.assertRaises(UnsupportedURLError):
                    get_scraper(url)



class HomeCurrencyTests(unittest.TestCase):
    def test_currency_detection(self):
        import currency
        cases = {"₹1,499": "INR", "INR 45,999.00": "INR", "Rs. 999": "INR", "$24.99": "USD",
                 "US$5": "USD", "CA$ 20": "CAD", "£51.77": "GBP", "1.299,00 €": "EUR", "USD": "USD",
                 "S$10": "SGD", "12.00": None, "": None}
        for text, code in cases.items():
            with self.subTest(text=text):
                self.assertEqual(currency.to_code(text), code)

    def test_conversion_and_cache(self):
        import currency
        self.assertEqual(currency.to_home(10, "₹"), 10)
        self.assertEqual(currency.to_home(10, None), 10)
        self.assertEqual(currency.to_home(10, "USD"), 860)

    def test_live_rate_is_used_when_available(self):
        import config, currency
        currency._cache.clear()
        fake = MagicMock()
        fake.json.return_value = {"rates": {"INR": 83.5}}
        with patch.object(config, "FX_LIVE_RATES", True), patch("currency.requests.get", return_value=fake):
            self.assertEqual(currency.to_home(2, "USD"), 167.0)
        currency._cache.clear()

    def test_live_rate_failure_falls_back(self):
        import config, currency, requests
        currency._cache.clear()
        with patch.object(config, "FX_LIVE_RATES", True), \
             patch("currency.requests.get", side_effect=requests.ConnectionError("offline")):
            self.assertEqual(currency.to_home(1, "USD"), 86.0)
        currency._cache.clear()

    def test_amazon_page_showing_inr_on_amazon_com(self):
        html = """<html><span id="productTitle">Lenovo Chromebook</span>
                  <span class="a-price"><span class="a-offscreen">INR 45,999.00</span></span></html>"""
        scraper = AmazonScraper()
        with patch.object(scraper, "fetch_html", return_value=html):
            data = scraper.scrape("https://www.amazon.com/dp/B0CVXYZ123")
        self.assertEqual((data["price"], data["currency"]), (45999.0, "₹"))

    def test_amazon_requests_prices_in_home_currency(self):
        self.assertIn("i18n-prefs=INR", AmazonScraper().get_headers("https://www.amazon.com/dp/B0CVXYZ123")["Cookie"])

    def test_european_number_format(self):
        self.assertEqual(AmazonScraper().extract_numeric_price("1.299,00 €"), 1299.0)


if __name__ == "__main__":
    unittest.main()
