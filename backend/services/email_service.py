"""Sends the price-drop email using Python's built-in smtplib."""
import logging
import smtplib
from email.message import EmailMessage

import config

logger = logging.getLogger(__name__)


def is_configured():
    return all([config.SMTP_HOST, config.SMTP_USER, config.SMTP_PASSWORD, config.EMAIL_TO])


def send_price_alert(product):
    """Returns True if the email was sent, False if not. Never raises, so a mail
    problem can't crash the monitoring thread. The password is never logged."""
    if not is_configured():
        logger.warning("Email not configured (check .env); skipped alert for product %s", product.id)
        return False

    clean_title = " ".join(product.title.split())  # no line breaks inside an email header
    symbol = config.CURRENCY_SYMBOL

    message = EmailMessage()
    message["Subject"] = f"PriceHawk: target reached for {clean_title}"
    message["From"] = config.SMTP_USER
    message["To"] = config.EMAIL_TO
    message.set_content(
        "Good news! A product you are tracking reached your target price.\n\n"
        f"Product:       {clean_title}\n"
        f"Current price: {symbol}{product.current_price:.2f}\n"
        f"Target price:  {symbol}{product.target_price:.2f}\n"
        f"Link:          {product.url}\n\n"
        "- PriceHawk"
    )

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
            server.starttls()  # encrypt the connection before logging in
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(message)
    except (smtplib.SMTPException, OSError) as error:
        logger.error("Email failed for product %s: %s", product.id, error)
        return False

    logger.info("Alert email sent for product %s", product.id)
    return True
