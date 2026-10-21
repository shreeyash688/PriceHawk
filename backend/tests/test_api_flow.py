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

    def track(self, url=BOOK_URL, target=15):
        return self.client.post("/api/products", json={"url": url, "target_price": target})

    # ----- tracking + validation -----
    def test_track_and_list(self):
        response = self.track()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["current_price"], 20.0)
        self.track(BOOK_URL_2, 10)
        products = self.client.get("/api/products").get_json()["products"]
        self.assertEqual(len(products), 2)

    def test_duplicate_is_409(self):
        self.track()
        self.assertEqual(self.track().status_code, 409)

    def test_invalid_target_prices_are_400(self):
        for bad in (-5, 0, "abc", None, True, float("nan")):
            with self.subTest(target=bad):
                self.assertEqual(self.track(target=bad).status_code, 400)

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
        empty = self.client.get("/api/export/products.csv").get_data(as_text=True)
        self.assertEqual(len(empty.strip().splitlines()), 1)  # header only

        product_id = self.track().get_json()["id"]
        products_csv = self.client.get("/api/export/products.csv").get_data(as_text=True)
        history_csv = self.client.get(f"/api/export/history.csv?product_id={product_id}").get_data(as_text=True)
        self.assertEqual(len(products_csv.strip().splitlines()), 2)
        self.assertEqual(len(history_csv.strip().splitlines()), 2)
        self.assertEqual(self.client.get("/api/export/history.csv?product_id=999").status_code, 404)

    def test_cors_only_for_extensions(self):
        extension = self.client.get("/api/health", headers={"Origin": "chrome-extension://abc"})
        website = self.client.get("/api/health", headers={"Origin": "https://evil.com"})
        self.assertEqual(extension.headers.get("Access-Control-Allow-Origin"), "chrome-extension://abc")
        self.assertIsNone(website.headers.get("Access-Control-Allow-Origin"))
