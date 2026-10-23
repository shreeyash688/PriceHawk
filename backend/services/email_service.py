"""Sends the price-drop email using Python's built-in smtplib."""
import logging
import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

import config

logger = logging.getLogger(__name__)

DUMMY_VALUES = {
    "your_email@gmail.com",
    "your_app_password_here",
    "your_email",
    "your_password",
    ""
}


_base_dir = getattr(config, "BASE_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_env_path = os.path.join(_base_dir, ".env")
_last_env_mtime = os.path.getmtime(_env_path) if os.path.exists(_env_path) else 0


def reload_config_from_env(force=False):
    """Reloads .env into config if the file was updated while the server is running."""
    global _last_env_mtime
    if os.path.exists(_env_path):
        try:
            mtime = os.path.getmtime(_env_path)
            if force or mtime > _last_env_mtime:
                _last_env_mtime = mtime
                load_dotenv(_env_path, override=True)
                config.SMTP_HOST = os.getenv("SMTP_HOST", getattr(config, "SMTP_HOST", "smtp.gmail.com"))
                try:
                    config.SMTP_PORT = int(os.getenv("SMTP_PORT", str(getattr(config, "SMTP_PORT", 587))))
                except (ValueError, TypeError):
                    pass
                config.SMTP_USER = os.getenv("SMTP_USER", getattr(config, "SMTP_USER", ""))
                config.SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", getattr(config, "SMTP_PASSWORD", ""))
        except OSError:
            pass


def is_configured():
    user = str(getattr(config, "SMTP_USER", "")).strip()
    password = str(getattr(config, "SMTP_PASSWORD", "")).strip()
    host = str(getattr(config, "SMTP_HOST", "")).strip()

    # If current memory has dummy or empty values, check if .env has been edited
    if not (host and user and password) or user.lower() in DUMMY_VALUES or password.lower() in DUMMY_VALUES:
        reload_config_from_env(force=False)
        user = str(getattr(config, "SMTP_USER", "")).strip()
        password = str(getattr(config, "SMTP_PASSWORD", "")).strip()
        host = str(getattr(config, "SMTP_HOST", "")).strip()

    if not (host and user and password):
        return False
    if user.lower() in DUMMY_VALUES or password.lower() in DUMMY_VALUES:
        return False
    return True


def send_price_alert(product):
    """Returns True if the email was sent, False if not. Never raises, so a mail
    problem can't crash the monitoring thread or price checking. The password is never logged."""
    if not is_configured():
        logger.warning(
            "Email not configured (check backend/.env); skipped alert for product %s",
            getattr(product, "id", "?")
        )
        return False

    user = str(getattr(config, "SMTP_USER", "")).strip()
    password = str(getattr(config, "SMTP_PASSWORD", "")).strip()
    host = str(getattr(config, "SMTP_HOST", "smtp.gmail.com")).strip()
    try:
        port = int(getattr(config, "SMTP_PORT", 587))
    except (ValueError, TypeError):
        port = 587

    clean_password = password.strip("\"'")
    # Google App Passwords may be entered with spaces between 4-char groups
    if "gmail.com" in host.lower() and len(clean_password.replace(" ", "")) == 16:
        clean_password = clean_password.replace(" ", "")

    clean_title = " ".join(str(product.title).split())  # no line breaks inside an email header
    symbol = getattr(config, "CURRENCY_SYMBOL", "£")

    message = EmailMessage()
    message["Subject"] = f"PriceHawk: target reached for {clean_title}"
    message["From"] = user
    message["To"] = product.notify_email  # each product has its own recipient
    message.set_content(
        "Good news! A product you are tracking reached your target price.\n\n"
        f"Product:       {clean_title}\n"
        f"Current price: {symbol}{product.current_price:.2f}\n"
        f"Target price:  {symbol}{product.target_price:.2f}\n"
        f"Link:          {product.url}\n\n"
        "- PriceHawk"
    )

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                server.login(user, clean_password)
                server.send_message(message)
        else:
            try:
                with smtplib.SMTP(host, port, timeout=15) as server:
                    server.starttls()  # encrypt the connection before logging in
                    server.login(user, clean_password)
                    server.send_message(message)
            except (smtplib.SMTPServerDisconnected, ConnectionResetError, OSError) as conn_err:
                logger.warning(
                    "SMTP connection on port %s failed (%s); attempting SSL fallback on port 465...",
                    port,
                    conn_err
                )
                with smtplib.SMTP_SSL(host, 465, timeout=15) as fallback_server:
                    fallback_server.login(user, clean_password)
                    fallback_server.send_message(message)
    except Exception as error:
        logger.error(
            "Email failed for product %s to %s: %s",
            getattr(product, "id", "?"),
            getattr(product, "notify_email", "?"),
            error
        )
        return False

    logger.info("Alert email sent for product %s to %s", product.id, product.notify_email)
    return True
