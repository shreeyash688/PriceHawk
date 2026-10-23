import smtplib
import unittest
from unittest.mock import patch

import config
from models.product import Product
from services import email_service


def make_product(email="buyer@x.com", url="http://books.toscrape.com/x", price=30.0, target=40.0):
    return Product(1, "A Light in the Attic", url, price, target,
                   1, 0, "t", "t", None, email)


SENDER = dict(SMTP_USER="sender@gmail.com", SMTP_PASSWORD="secret")


class EmailServiceTests(unittest.TestCase):
    def test_email_goes_to_the_products_own_recipient(self):
        with patch.multiple(config, **SENDER), patch("services.email_service.smtplib.SMTP") as smtp:
            server = smtp.return_value.__enter__.return_value
            self.assertTrue(email_service.send_price_alert(make_product("buyer@x.com")))
            message = server.send_message.call_args[0][0]
            self.assertEqual(message["To"], "buyer@x.com")
            self.assertEqual(message["From"], "PriceHawk <sender@gmail.com>")
            self.assertIn("£30.00", message.get_body(("plain",)).get_content())

    def test_indian_stores_are_emailed_in_rupees(self):
        for url in ("https://www.amazon.in/dp/B0DXNT1234",
                    "https://www.flipkart.com/x/p/itm123",
                    "https://www.myntra.com/shirts/x/12345678/buy"):
            with self.subTest(url=url), patch.multiple(config, **SENDER), \
                 patch("services.email_service.smtplib.SMTP") as smtp:
                product = make_product(url=url, price=1499.0, target=1500.0)
                self.assertTrue(email_service.send_price_alert(product))
                message = smtp.return_value.__enter__.return_value.send_message.call_args[0][0]
                for part in ("plain", "html"):
                    body = message.get_body((part,)).get_content()
                    self.assertIn("₹1,499.00", body)
                    self.assertNotIn("£", body)
                    self.assertNotIn("€", body)
                self.assertIn("₹1,499.00", message["Subject"])

    def test_html_part_escapes_the_title(self):
        product = make_product()
        product.title = "<script>alert(1)</script>"
        html_body = email_service.build_message(product, "s@x.com").get_body(("html",)).get_content()
        self.assertNotIn("<script>", html_body)

    def test_wrong_password_does_not_retry_on_465(self):
        with patch.multiple(config, SMTP_PORT=587, **SENDER), \
             patch("services.email_service.smtplib.SMTP",
                   side_effect=smtplib.SMTPAuthenticationError(535, b"bad")), \
             patch("services.email_service.smtplib.SMTP_SSL") as smtp_ssl:
            self.assertFalse(email_service.send_price_alert(make_product()))
            smtp_ssl.assert_not_called()

    def test_blocked_port_falls_back_to_ssl(self):
        with patch.multiple(config, SMTP_PORT=587, **SENDER), \
             patch("services.email_service.smtplib.SMTP", side_effect=ConnectionRefusedError()), \
             patch("services.email_service.smtplib.SMTP_SSL") as smtp_ssl:
            self.assertTrue(email_service.send_price_alert(make_product()))
            smtp_ssl.assert_called_with("smtp.gmail.com", 465, timeout=15)

    def test_not_configured_returns_false(self):
        with patch.multiple(config, SMTP_USER="", SMTP_PASSWORD=""):
            self.assertFalse(email_service.send_price_alert(make_product()))

    def test_smtp_errors_return_false(self):
        for error in (smtplib.SMTPAuthenticationError(535, b"bad"), ConnectionRefusedError()):
            with self.subTest(error=type(error).__name__):
                with patch.multiple(config, **SENDER), \
                     patch("services.email_service.smtplib.SMTP", side_effect=error), \
                     patch("services.email_service.smtplib.SMTP_SSL", side_effect=error):
                    self.assertFalse(email_service.send_price_alert(make_product()))

    def test_dummy_credentials_detected_as_not_configured(self):
        with patch.multiple(config, SMTP_USER="your_email@gmail.com", SMTP_PASSWORD="your_app_password_here"):
            self.assertFalse(email_service.is_configured())
            self.assertFalse(email_service.send_price_alert(make_product()))

    def test_port_465_uses_ssl(self):
        with patch.multiple(config, SMTP_HOST="smtp.gmail.com", SMTP_PORT=465, **SENDER), \
             patch("services.email_service.smtplib.SMTP_SSL") as smtp_ssl:
            server = smtp_ssl.return_value.__enter__.return_value
            self.assertTrue(email_service.send_price_alert(make_product("buyer@x.com")))
            smtp_ssl.assert_called_with("smtp.gmail.com", 465, timeout=15)
            server.login.assert_called_with("sender@gmail.com", "secret")

    def test_gmail_app_password_with_spaces_is_cleaned(self):
        spaced_sender = dict(SMTP_USER="sender@gmail.com", SMTP_PASSWORD="abcd efgh ijkl mnop")
        with patch.multiple(config, SMTP_HOST="smtp.gmail.com", SMTP_PORT=587, **spaced_sender), \
             patch("services.email_service.smtplib.SMTP") as smtp:
            server = smtp.return_value.__enter__.return_value
            self.assertTrue(email_service.send_price_alert(make_product("buyer@x.com")))
            server.login.assert_called_with("sender@gmail.com", "abcdefghijklmnop")

    def test_unexpected_exception_returns_false_safely(self):
        with patch.multiple(config, **SENDER), \
             patch("services.email_service.smtplib.SMTP", side_effect=RuntimeError("unexpected crash")):
            self.assertFalse(email_service.send_price_alert(make_product()))


if __name__ == "__main__":
    unittest.main()

