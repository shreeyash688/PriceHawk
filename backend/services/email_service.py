"""Sends the price-drop email using Python's built-in smtplib.

The email is sent in two versions (plain text + HTML) and always uses the
product's own store currency, e.g. ₹ for Amazon.in, Flipkart and Myntra.
"""
import html
import logging
import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

import config

logger = logging.getLogger(__name__)

# Placeholder values from .env.example: treated as "not configured".
DUMMY_VALUES = {"your_email@gmail.com", "your_app_password_here", "your_email", "your_password", ""}

_ENV_PATH = os.path.join(config.BASE_DIR, ".env")
_last_env_mtime = os.path.getmtime(_ENV_PATH) if os.path.exists(_ENV_PATH) else 0


def reload_config_from_env(force=False):
    """Re-read SMTP settings if backend/.env was edited while the server is running."""
    global _last_env_mtime
    try:
        mtime = os.path.getmtime(_ENV_PATH)
    except OSError:
        return
    if not force and mtime <= _last_env_mtime:
        return
    _last_env_mtime = mtime
    load_dotenv(_ENV_PATH, override=True)
    config.SMTP_HOST = os.getenv("SMTP_HOST", config.SMTP_HOST)
    config.SMTP_USER = os.getenv("SMTP_USER", config.SMTP_USER)
    config.SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", config.SMTP_PASSWORD)
    try:
        config.SMTP_PORT = int(os.getenv("SMTP_PORT", str(config.SMTP_PORT)))
    except ValueError:
        pass


def _credentials():
    return (str(config.SMTP_HOST).strip(), str(config.SMTP_USER).strip(),
            str(config.SMTP_PASSWORD).strip())


def _looks_configured(host, user, password):
    return bool(host and user and password) and user.lower() not in DUMMY_VALUES \
        and password.lower() not in DUMMY_VALUES


def is_configured():
    if not _looks_configured(*_credentials()):
        reload_config_from_env()  # maybe .env was filled in after start-up
    return _looks_configured(*_credentials())


def _clean_password(host, password):
    password = password.strip("\"'")
    # Google App Passwords are often pasted as "abcd efgh ijkl mnop"
    if "gmail.com" in host.lower() and len(password.replace(" ", "")) == 16:
        password = password.replace(" ", "")
    return password


# ---------- message ----------

def build_message(product, sender):
    """Create the alert email (plain text + HTML) for one product."""
    title = " ".join(str(product.title).split())  # no line breaks inside an email header
    now, target = product.format_price(product.current_price), product.format_price(product.target_price)
    saving = product.format_price(max(product.target_price - product.current_price, 0))
    store = product.retailer or "the store"

    message = EmailMessage()
    message["Subject"] = f"Price drop: {title[:80]} is now {now}"
    message["From"] = f"PriceHawk <{sender}>"
    message["To"] = product.notify_email  # each product has its own recipient
    message.set_content(
        "Good news! A product you are tracking reached your target price.\n\n"
        f"Product:       {title}\n"
        f"Store:         {store}\n"
        f"Current price: {now}\n"
        f"Your target:   {target}\n"
        f"Link:          {product.url}\n\n"
        "- PriceHawk"
    )

    safe = {key: html.escape(value) for key, value in
            dict(title=title, now=now, target=target, saving=saving, store=store, url=product.url).items()}
    message.add_alternative(f"""\
<!doctype html>
<html><body style="margin:0;padding:24px;background:#f4f2f7;font-family:Segoe UI,Arial,sans-serif;color:#17151b">
  <table role="presentation" width="100%" style="max-width:480px;margin:0 auto;background:#ffffff;border-radius:14px;overflow:hidden">
    <tr><td style="background:#141217;padding:18px 24px;color:#ffb800;font-weight:700;font-size:18px">PriceHawk</td></tr>
    <tr><td style="padding:24px">
      <p style="margin:0 0 6px;font-size:13px;color:#6f6b7d">Target reached on {safe['store']}</p>
      <h1 style="margin:0 0 18px;font-size:18px;line-height:1.35">{safe['title']}</h1>
      <table role="presentation" width="100%" style="border-collapse:collapse;margin-bottom:20px">
        <tr>
          <td style="padding:12px;background:#f4f2f7;border-radius:10px">
            <div style="font-size:12px;color:#6f6b7d">Price now</div>
            <div style="font-size:24px;font-weight:700;color:#0f8a5f">{safe['now']}</div>
          </td>
          <td style="width:12px"></td>
          <td style="padding:12px;background:#f4f2f7;border-radius:10px">
            <div style="font-size:12px;color:#6f6b7d">Your target</div>
            <div style="font-size:24px;font-weight:700">{safe['target']}</div>
          </td>
        </tr>
      </table>
      <p style="margin:0 0 20px;font-size:14px">That's {safe['saving']} below your target.</p>
      <a href="{safe['url']}" style="display:inline-block;background:#ffb800;color:#1a1400;text-decoration:none;font-weight:600;padding:12px 20px;border-radius:10px">View product</a>
    </td></tr>
    <tr><td style="padding:14px 24px;font-size:12px;color:#6f6b7d;border-top:1px solid #ece9f1">
      You get one email per price drop. Pause or remove this product from the PriceHawk extension.
    </td></tr>
  </table>
</body></html>
""", subtype="html")
    return message


# ---------- sending ----------

def _send_ssl(host, port, user, password, message):
    with smtplib.SMTP_SSL(host, port, timeout=15) as server:
        server.login(user, password)
        server.send_message(message)


def _send_starttls(host, port, user, password, message):
    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls()  # encrypt the connection before logging in
        server.login(user, password)
        server.send_message(message)


def send_price_alert(product):
    """Returns True if the email was sent, False if not. Never raises, so a mail
    problem can't crash the monitoring thread. The password is never logged."""
    if not is_configured():
        logger.warning("Email not configured (check backend/.env); skipped alert for product %s",
                       getattr(product, "id", "?"))
        return False

    host, user, password = _credentials()
    password = _clean_password(host, password)
    try:
        port = int(config.SMTP_PORT)
    except (TypeError, ValueError):
        port = 587

    try:
        message = build_message(product, user)
        if port == 465:
            _send_ssl(host, port, user, password, message)
        else:
            try:
                _send_starttls(host, port, user, password, message)
            except smtplib.SMTPAuthenticationError:
                raise  # wrong user/password: trying another port will not help
            except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, ConnectionError, TimeoutError) as error:
                # Some networks block port 587; Gmail also accepts SSL on 465.
                logger.warning("SMTP on port %s failed (%s); retrying with SSL on 465", port, error)
                _send_ssl(host, 465, user, password, message)
    except smtplib.SMTPAuthenticationError:
        logger.error("Email login failed for %s. Check SMTP_USER / SMTP_PASSWORD "
                     "(Gmail needs an App Password).", user)
        return False
    except Exception as error:
        logger.error("Email failed for product %s to %s: %s",
                     getattr(product, "id", "?"), getattr(product, "notify_email", "?"), error)
        return False

    logger.info("Alert email sent for product %s to %s", product.id, product.notify_email)
    return True
