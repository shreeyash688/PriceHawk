import smtplib
import unittest
from unittest.mock import patch

import config
from models.product import Product
from services import email_service


def make_product(email="buyer@x.com"):
    return Product(1, "A Light in the Attic", "http://books.toscrape.com/x", 30.0, 40.0,
                   1, 0, "t", "t", None, email)


SENDER = dict(SMTP_USER="sender@gmail.com", SMTP_PASSWORD="secret")


class EmailServiceTests(unittest.TestCase):
    def test_email_goes_to_the_products_own_recipient(self):
        with patch.multiple(config, **SENDER), patch("services.email_service.smtplib.SMTP") as smtp:
            server = smtp.return_value.__enter__.return_value
            self.assertTrue(email_service.send_price_alert(make_product("buyer@x.com")))
            message = server.send_message.call_args[0][0]
            self.assertEqual(message["To"], "buyer@x.com")
            self.assertEqual(message["From"], "sender@gmail.com")
            self.assertIn("£30.00", message.get_content())

    def test_not_configured_returns_false(self):
        with patch.multiple(config, SMTP_USER="", SMTP_PASSWORD=""):
            self.assertFalse(email_service.send_price_alert(make_product()))

    def test_smtp_errors_return_false(self):
        for error in (smtplib.SMTPAuthenticationError(535, b"bad"), ConnectionRefusedError()):
            with self.subTest(error=type(error).__name__):
                with patch.multiple(config, **SENDER), \
                     patch("services.email_service.smtplib.SMTP", side_effect=error):
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

