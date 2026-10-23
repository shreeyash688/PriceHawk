"""End-to-end tests of the API using a fake scraper and a fake email sender."""
from unittest.mock import patch

import app as app_module
import config
from tests.helpers import BOOK_URL, BOOK_URL_2, DatabaseTestCase, FakeScraper


class ApiFlowTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.client = app_module.app.test_client()
        self.scraper = FakeScraper(price=20.00)

        scraper_patch = patch("services.tracker_service.get_scraper", return_value=self.scraper)
        email_patch = patch("services.tracker_service.email_service.send_price_alert", return_value=True)
        demo_patch = patch.object(config, "DEMO_MODE", True)
        scraper_patch.start()
        self.send_email = email_patch.start()
        demo_patch.start()
        for p in (scraper_patch, email_patch, demo_patch):
            self.addCleanup(p.stop)

    def track(self, url=BOOK_URL, target=15, email="a@x.com"):
        return self.client.post("/api/products", json={"url": url, "target_price": target, "email": email})

    # ----- tracking + validation -----
    def test_track_and_list(self):
        response = self.track()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["current_price"], 20.0)
        self.track(BOOK_URL_2, 10)
        products = self.client.get("/api/products?email=a@x.com").get_json()["products"]
        self.assertEqual(len(products), 2)

    def test_duplicate_is_409(self):
        self.track()
        self.assertEqual(self.track().status_code, 409)

    def test_invalid_target_prices_are_400(self):
        for bad in (-5, 0, "abc", None, True, float("nan")):
            with self.subTest(target=bad):
                self.assertEqual(self.track(target=bad).status_code, 400)

    # ----- multiple people (one email per product) -----
    def test_same_book_for_different_people(self):
        self.assertEqual(self.track(email="a@x.com").status_code, 201)
        self.assertEqual(self.track(email="b@x.com").status_code, 201)
        mine = self.client.get("/api/products?email=a@x.com").get_json()["products"]
        theirs = self.client.get("/api/products?email=b@x.com").get_json()["products"]
        self.assertEqual([p["notify_email"] for p in mine], ["a@x.com"])
        self.assertEqual([p["notify_email"] for p in theirs], ["b@x.com"])

    def test_email_is_cleaned_up(self):
        product = self.track(email="  Person@Example.COM ").get_json()
        self.assertEqual(product["notify_email"], "person@example.com")

    def test_invalid_emails_are_400(self):
        bad_emails = ["", None, "abc", "a@b", "a b@x.com", "a,b@x.com", "a@x.com,evil@y.com",
                      "a@x.com\nBcc: evil@y.com", 123, "@x.com", "a@.com"]
        for bad in bad_emails:
            with self.subTest(email=bad):
                self.assertEqual(self.track(email=bad).status_code, 400)

    def test_list_and_exports_need_an_email(self):
        self.assertEqual(self.client.get("/api/products").status_code, 400)
        self.assertEqual(self.client.get("/api/export/products.csv").status_code, 400)
        self.assertEqual(self.client.get("/api/export/history.csv").status_code, 400)

    def test_limit_per_email(self):
        with patch.object(config, "MAX_PRODUCTS_PER_EMAIL", 1):
            self.assertEqual(self.track(BOOK_URL, email="a@x.com").status_code, 201)
            full = self.track(BOOK_URL_2, email="a@x.com")
            self.assertEqual(full.status_code, 400)
            self.assertEqual(full.get_json()["code"], "limit_reached")
            self.assertNotIn("already tracking", full.get_json()["error"])  # never looks like a duplicate
            self.assertEqual(self.track(BOOK_URL_2, email="b@x.com").status_code, 201)

    def test_duplicate_wins_over_full_list(self):
        with patch.object(config, "MAX_PRODUCTS_PER_EMAIL", 1):
            self.track(BOOK_URL, email="a@x.com")
            again = self.track(BOOK_URL, email="a@x.com")
            self.assertEqual((again.status_code, again.get_json()["code"]), (409, "duplicate"))

    def test_alert_goes_to_the_owner_of_the_product(self):
        self.track(target=25, email="a@x.com")  # price 20 <= 25 -> alert
        self.track(target=10, email="b@x.com")  # 20 > 10 -> no alert
        self.assertEqual(self.send_email.call_count, 1)
        alerted_product = self.send_email.call_args[0][0]
        self.assertEqual(alerted_product.notify_email, "a@x.com")

    def test_preview_says_if_email_already_tracks_it(self):
        self.track(email="a@x.com")
        body = lambda email: {"url": BOOK_URL, "email": email}
        self.assertTrue(self.client.post("/api/preview", json=body("a@x.com")).get_json()["already_tracked"])
        self.assertFalse(self.client.post("/api/preview", json=body("b@x.com")).get_json()["already_tracked"])
        self.assertFalse(self.client.post("/api/preview", json={"url": BOOK_URL}).get_json()["already_tracked"])

    def test_bad_body_is_400(self):
        response = self.client.post("/api/products", data="not json", content_type="text/plain")
        self.assertEqual(response.status_code, 400)

    def test_unknown_product_is_404(self):
        self.assertEqual(self.client.get("/api/products/999").status_code, 404)
        self.assertEqual(self.client.delete("/api/products/999").status_code, 404)

    # ----- alerts -----
    def test_price_above_target_sends_nothing(self):
        self.track(target=15)
        self.send_email.assert_not_called()

    def test_equal_and_below_target_alert(self):
        self.track(target=20)  # price 20 == target 20
        self.assertEqual(self.send_email.call_count, 1)

    def test_no_repeat_alerts_then_rearms(self):
        product_id = self.track(target=15).get_json()["id"]
        check = lambda: self.client.post(f"/api/products/{product_id}/check")

        self.scraper.price = 12.0
        check(); check(); check()                       # three polling rounds below target
        self.assertEqual(self.send_email.call_count, 1)  # ...but only ONE email

        self.scraper.price = 18.0
        check()                                          # price recovers -> re-armed
        self.scraper.price = 11.0
        check()                                          # drops again -> new email
        self.assertEqual(self.send_email.call_count, 2)

    def test_failed_email_is_retried(self):
        product_id = self.track(target=15).get_json()["id"]
        self.send_email.return_value = False
        self.scraper.price = 10.0
        self.client.post(f"/api/products/{product_id}/check")
        self.assertFalse(self.client.get(f"/api/products/{product_id}").get_json()["alert_sent"])
        self.send_email.return_value = True
        self.client.post(f"/api/products/{product_id}/check")
        self.assertTrue(self.client.get(f"/api/products/{product_id}").get_json()["alert_sent"])

    def test_check_now_succeeds_even_when_smtp_fails(self):
        product_id = self.track(target=25).get_json()["id"]
        self.scraper.price = 10.0
        self.send_email.return_value = False
        response = self.client.post(f"/api/products/{product_id}/check")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["current_price"], 10.0)
        history = self.client.get(f"/api/products/{product_id}/history").get_json()["history"]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[-1]["price"], 10.0)

    # ----- history, update, delete, background -----
    def test_history_and_update_and_delete(self):
        product_id = self.track().get_json()["id"]
        self.client.post(f"/api/products/{product_id}/check")
        history = self.client.get(f"/api/products/{product_id}/history").get_json()["history"]
        self.assertEqual(len(history), 2)

        updated = self.client.put(f"/api/products/{product_id}", json={"target_price": 12.5}).get_json()
        self.assertEqual(updated["target_price"], 12.5)
        self.assertEqual(self.client.put(f"/api/products/{product_id}", json={}).status_code, 400)

        self.assertEqual(self.client.delete(f"/api/products/{product_id}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/products/{product_id}").status_code, 404)

    def test_background_check_skips_paused_and_survives_errors(self):
        from services import tracker_service
        first = self.track(BOOK_URL).get_json()["id"]
        second = self.track(BOOK_URL_2).get_json()["id"]
        self.client.put(f"/api/products/{second}", json={"tracking_active": False})

        self.scraper.price = 18.0
        self.assertEqual(tracker_service.check_all_products(), 1)  # only the active one
        self.assertEqual(self.client.get(f"/api/products/{first}").get_json()["current_price"], 18.0)
        self.assertEqual(self.client.get(f"/api/products/{second}").get_json()["current_price"], 20.0)

    def test_scrape_failure_is_recorded(self):
        from exceptions import ScraperError
        product_id = self.track().get_json()["id"]
        self.scraper.scrape = lambda url: (_ for _ in ()).throw(ScraperError("site down"))
        response = self.client.post(f"/api/products/{product_id}/check")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.client.get(f"/api/products/{product_id}").get_json()["last_error"], "site down")

    # ----- demo mode -----
    def test_simulate_price_triggers_alert(self):
        product_id = self.track(target=15).get_json()["id"]
        response = self.client.post(f"/api/products/{product_id}/simulate", json={"price": 9.99})
        self.assertEqual(response.get_json()["current_price"], 9.99)
        self.assertEqual(self.send_email.call_count, 1)

    def test_simulate_blocked_when_demo_off(self):
        product_id = self.track().get_json()["id"]
        with patch.object(config, "DEMO_MODE", False):
            response = self.client.post(f"/api/products/{product_id}/simulate", json={"price": 1})
        self.assertEqual(response.status_code, 403)

    # ----- CSV + CORS -----
    def test_csv_export_with_and_without_data(self):
        empty = self.client.get("/api/export/products.csv?email=a@x.com").get_data(as_text=True)
        self.assertEqual(len(empty.strip().splitlines()), 1)  # header only

        product_id = self.track().get_json()["id"]
        products_csv = self.client.get("/api/export/products.csv?email=a@x.com").get_data(as_text=True)
        history_csv = self.client.get(
            f"/api/export/history.csv?email=a@x.com&product_id={product_id}").get_data(as_text=True)
        other_persons_csv = self.client.get("/api/export/products.csv?email=b@x.com").get_data(as_text=True)
        self.assertEqual(len(other_persons_csv.strip().splitlines()), 1)  # header only: not their products
        self.assertEqual(len(products_csv.strip().splitlines()), 2)
        history_lines = history_csv.strip().splitlines()
        self.assertEqual(len(history_lines), 2)
        self.assertIn("20", history_lines[1])
        self.assertEqual(self.client.get("/api/export/history.csv?email=a@x.com&product_id=999").status_code, 404)

    def test_cors_only_for_extensions(self):
        extension = self.client.get("/api/health", headers={"Origin": "chrome-extension://abc"})
        website = self.client.get("/api/health", headers={"Origin": "https://evil.com"})
        self.assertEqual(extension.headers.get("Access-Control-Allow-Origin"), "chrome-extension://abc")
        self.assertIsNone(website.headers.get("Access-Control-Allow-Origin"))

    def test_readd_product_after_deletion(self):
        # 1. Track product
        first = self.track(BOOK_URL, target=15, email="a@x.com").get_json()
        first_id = first["id"]
        self.assertEqual(first["current_price"], 20.0)

        # 2. Delete product
        del_res = self.client.delete(f"/api/products/{first_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(self.client.get(f"/api/products/{first_id}").status_code, 404)

        # 3. Re-track same product with fresh price
        self.scraper.price = 25.0
        second = self.track(BOOK_URL, target=15, email="a@x.com").get_json()
        self.assertNotEqual(second["id"], first_id)
        self.assertEqual(second["current_price"], 25.0)

        # List shows only the fresh product
        products = self.client.get("/api/products?email=a@x.com").get_json()["products"]
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["id"], second["id"])
        self.assertEqual(products[0]["current_price"], 25.0)

    def test_pause_and_resume_tracking(self):
        product_id = self.track().get_json()["id"]
        # Pause
        paused = self.client.put(f"/api/products/{product_id}", json={"tracking_active": False}).get_json()
        self.assertFalse(paused["tracking_active"])
        # Resume
        resumed = self.client.put(f"/api/products/{product_id}", json={"tracking_active": True}).get_json()
        self.assertTrue(resumed["tracking_active"])

    def test_bad_update_changes_nothing(self):
        product_id = self.track(target=15).get_json()["id"]
        response = self.client.put(f"/api/products/{product_id}",
                                   json={"target_price": 99, "tracking_active": "no"})
        self.assertEqual(response.status_code, 400)
        product = self.client.get(f"/api/products/{product_id}").get_json()
        self.assertEqual(product["target_price"], 15)  # target NOT half-applied

    def test_product_json_includes_currency_and_store(self):
        product = self.track().get_json()
        self.assertEqual(product["currency"], "₹")  # every price is in the home currency
        self.assertEqual(product["retailer"], "Books to Scrape")

    # ----- browser page data (store blocks the server) -----
    def test_track_with_page_data_never_scrapes(self):
        url = "https://www.amazon.com/Lenovo-Chromebook/dp/B0CVXYZ123?ref=x"
        with patch("services.tracker_service.get_scraper", wraps=__import__("scrapers").get_scraper) as gs, \
             patch("scrapers.base_scraper.BaseScraper.fetch_html", side_effect=AssertionError("no scraping")):
            response = self.client.post("/api/products", json={
                "url": url, "target_price": 40000, "email": "a@x.com",
                "page": {"title": "Lenovo Chromebook", "price": 45999, "currency": "INR"}})
        self.assertEqual(response.status_code, 201, response.get_json())
        body = response.get_json()
        self.assertEqual(body["url"], "https://www.amazon.com/dp/B0CVXYZ123")
        self.assertEqual(body["current_price"], 45999)
        self.assertEqual(body["currency"], "₹")

    def test_page_prices_in_dollars_are_converted_to_rupees(self):
        data = self.client.post("/api/preview", json={
            "url": "https://www.amazon.com/dp/B0CVXYZ123",
            "page": {"title": "Laptop", "price": 100, "currency": "USD"}}).get_json()
        self.assertEqual(data["currency"], "₹")
        self.assertEqual(data["price"], 8600.0)  # built-in test rate: 1 USD = 86 INR
        self.assertEqual(data["original_price"], 100)
        self.assertEqual(data["original_currency"], "$")
        self.assertTrue(data["converted"])

    def test_bad_page_data_is_400(self):
        for page in ("x", {"price": 10}, {"title": "T", "price": -1}, {"title": "T", "price": 5, "currency": "x" * 20}):
            with self.subTest(page=page):
                response = self.client.post("/api/preview", json={"url": BOOK_URL, "page": page})
                self.assertEqual(response.status_code, 400)

    def test_page_data_still_checks_the_url(self):
        import scrapers
        for url in ("http://169.254.169.254/latest", "https://www.amazon.com/s?k=mouse"):
            with self.subTest(url=url), patch("services.tracker_service.get_scraper", scrapers.get_scraper):
                response = self.client.post("/api/preview", json={"url": url, "page": {"title": "x", "price": 1}})
                self.assertEqual(response.status_code, 400)

    def test_observe_records_price_and_alerts(self):
        self.track(target=15)  # scraper says 20
        response = self.client.post("/api/products/observe", json={
            "url": BOOK_URL, "email": "a@x.com", "page": {"title": "Book", "price": 12, "currency": "INR"}})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["current_price"], 12)
        self.assertTrue(body["alert_sent"])
        self.send_email.assert_called_once()
        history = self.client.get(f"/api/products/{body['id']}/history").get_json()["history"]
        self.assertEqual([h["price"] for h in history], [20, 12])

    def test_observe_untracked_is_404(self):
        response = self.client.post("/api/products/observe", json={
            "url": BOOK_URL, "email": "nobody@x.com", "page": {"title": "Book", "price": 12}})
        self.assertEqual(response.status_code, 404)

    def test_health_reports_currency(self):
        body = self.client.get("/api/health").get_json()
        self.assertEqual((body["currency"], body["currency_symbol"]), ("INR", "₹"))
        self.assertEqual(body["version"], config.VERSION)

    def test_monitor_backs_off_after_a_captcha(self):
        from exceptions import ScraperError
        from services import tracker_service
        product_id = self.track().get_json()["id"]
        self.scraper.scrape = lambda url: (_ for _ in ()).throw(ScraperError("Amazon anti-bot verification or CAPTCHA detected."))
        self.assertEqual(tracker_service.check_all_products(), 0)  # blocked -> error recorded
        calls = []
        self.scraper.scrape = lambda url: calls.append(url) or {"url": url, "title": "t", "price": 5}
        tracker_service.check_all_products()
        self.assertEqual(calls, [])  # within BLOCKED_RETRY_MINUTES: not retried
        with patch.object(config, "BLOCKED_RETRY_MINUTES", 0):
            tracker_service.check_all_products()
        self.assertEqual(len(calls), 1)  # after the pause it is checked again
        self.assertIsNone(self.client.get(f"/api/products/{product_id}").get_json()["last_error"])
