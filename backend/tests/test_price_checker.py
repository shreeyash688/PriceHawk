import unittest

from services.tracker_service import PriceChecker


class PriceCheckerTests(unittest.TestCase):
    def test_price_above_target(self):
        self.assertFalse(PriceChecker.is_target_reached(20.00, 15.00))

    def test_price_equal_to_target(self):
        self.assertTrue(PriceChecker.is_target_reached(15.00, 15.00))

    def test_price_below_target(self):
        self.assertTrue(PriceChecker.is_target_reached(10.00, 15.00))

    def test_alert_only_once(self):
        self.assertTrue(PriceChecker.should_send_alert(10, 15, alert_already_sent=False))
        self.assertFalse(PriceChecker.should_send_alert(10, 15, alert_already_sent=True))

    def test_alert_resets_when_price_goes_back_up(self):
        self.assertTrue(PriceChecker.should_reset_alert(20, 15, alert_already_sent=True))
        self.assertFalse(PriceChecker.should_reset_alert(10, 15, alert_already_sent=True))


if __name__ == "__main__":
    unittest.main()
