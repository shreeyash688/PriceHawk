# PriceHawk 🦅
**Track Prices. Catch Deals. Save Money.**

A Chrome extension + Python (Flask) backend. Open a product page, set a target price and your email.
The backend stores the product in Supabase, re-checks the price in a background thread, and emails you
**once** when the price reaches your target.

**Supported stores:** Amazon (amazon.in, .com, .co.uk, …), Flipkart, Myntra, eBay, and Books to Scrape (practice site).
Every price is stored, shown and emailed in **rupees (₹)**: set by `HOME_CURRENCY=INR` in `.env`.
Stores that answer in another currency (e.g. Amazon.com in USD) are converted with a live exchange rate
(cached 6 h, built-in approximate rates if offline). The popup shows the original, e.g. "converted from $539.99".

### When a store blocks the server (Amazon CAPTCHA)
Amazon often blocks requests from the Python backend. PriceHawk works around it with the user's own browser:
- **Tracking:** the popup reads the title and price from the open page and sends them with the link,
  so the backend doesn't need to scrape at all (the link is still validated).
- **Check now:** if the server is blocked, the popup reads the page through the browser (a quick fetch,
  then a hidden background tab) and records that price with `POST /api/products/observe`.
- **Opening the Tracked tab** quietly refreshes blocked products through the browser.
- **Opening the popup on a product you track** records the price you're looking at.
Alerts work exactly the same whichever way the price arrives.

## 1. Database (Supabase) — once
1. Create a Supabase project.
2. Dashboard → **SQL Editor** → paste `backend/database/schema.sql` → **Run**.
3. Dashboard → Project Settings → API: copy the **Project URL** and the **secret / service_role key**.

## 2. Backend setup
```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env         # Mac/Linux: cp .env.example .env   -> then fill it in
python app.py                  # API runs at http://127.0.0.1:5000
```
Run the tests (no internet, database or email needed): `cd backend && python -m unittest -v`

**Gmail:** turn on 2-Step Verification, create an *App Password*, and put it in `SMTP_PASSWORD`.
That account is only the **sender**. Each person types their **own email** in the extension, and alerts go there.

## 3. Load the extension
`chrome://extensions` → turn on **Developer mode** → **Load unpacked** → choose the `extension/` folder.
Optional: copy the extension ID into `EXTENSION_ID` in `.env` so only your extension can call the API.

## Using it
- **Track tab:** the popup reads the product on the current page (title, price, store). Pick a target
  (or tap *5% / 10% / 20% off*), enter your email, press **Start tracking**. Not on a product page?
  Paste a link and press **Preview**.
- **Tracked tab:** every product shows now vs. target, how far it is from the target, and when it was last
  checked. Actions: **Check now**, **Pause/Resume**, **History** (chart + list + CSV), edit target (✎), remove (🗑, click twice).
  Sort by *Newest* or *Closest to target*.
- Header buttons export all your products / all price history as CSV.

## Folder map
| Path | Job |
|---|---|
| `backend/app.py` | Flask routes, `handle_errors` decorator, CORS, start-up |
| `backend/config.py` | Settings from `.env` |
| `backend/exceptions.py` | Custom errors (each knows its HTTP status code) |
| `backend/scrapers/base_scraper.py` | Abstract `BaseScraper`: download, JSON-LD, price parsing, `currency_for_url` |
| `backend/scrapers/*_scraper.py` | One subclass per store: URL allow-list + page parsing |
| `backend/scrapers/__init__.py` | `get_scraper(url)`, `currency_for_url(url)` |
| `backend/currency.py` | Detect currencies in price text, convert to `HOME_CURRENCY` (live rate + cache + fallback) |
| `backend/models/product.py` | `Product` class (`currency`, `price_gap`, `to_dict`, …) |
| `backend/database/schema.sql` | Supabase/PostgreSQL tables (run once) |
| `backend/database/db.py` | All database CRUD (Supabase client) |
| `backend/services/tracker_service.py` | `PriceChecker` + track / check / alert logic |
| `backend/services/monitor.py` | Background thread |
| `backend/services/email_service.py` | SMTP email (plain text + HTML) |
| `backend/services/export_service.py` | CSV export (generators) |
| `backend/tests/` | 129 automated tests (Supabase, websites and exchange rates are mocked) |
| `extension/` | `manifest.json`, `popup.html/css/js`, icons |

## API (for the extension)
All responses are JSON. Errors look like `{"error": "message"}` with status 400 (bad input), 404, 409 (already tracked), 502 (website problem).

| Method + URL | Body | What it does |
|---|---|---|
| `GET /api/health` | | Is the backend running? (+ `demo_mode`, `currency`) |
| `POST /api/preview` | `{"url", "email"?, "page"?}` | Title + price in ₹ **without** saving (+ `original_price`, `already_tracked`) |
| `POST /api/products` | `{"url", "target_price", "email", "page"?}` | Start tracking (201) |
| `POST /api/products/observe` | `{"url", "email", "page"}` | Record a price the browser read for a product this email tracks |
| `GET /api/products?email=&sort=newest\|deals` | | That email's products (`deals` = closest to target first) |
| `GET /api/products/<id>` | | One product |
| `PUT /api/products/<id>` | `{"target_price"?, "tracking_active"?}` | Change target / pause / resume (all-or-nothing) |
| `DELETE /api/products/<id>` | | Stop tracking and delete |
| `POST /api/products/<id>/check` | | "Check now" |
| `GET /api/products/<id>/history` | | Price history |
| `GET /api/export/products.csv?email=` | | CSV of that email's products |
| `GET /api/export/history.csv?email=&product_id=` | | CSV of that email's history (optionally one product) |
| `POST /api/products/<id>/simulate` | `{"price"}` | **Demo mode only**: fake a price |

`page` = what the extension read from the open page: `{"title", "price", "currency"?}` (currency as code or symbol, e.g. `"INR"`, `"$"`).
When `page` is sent, the backend validates the link but doesn't scrape. Known limit: a user could send a fake
price, but it only affects their own tracking.

A product looks like: `{id, title, url, retailer, currency, notify_email, current_price, target_price, price_gap, tracking_active, alert_sent, created_at, last_checked_at, last_error}`.

## Demo (without waiting for a real price change)
1. In `.env`: `DEMO_MODE=true`, then start the server.
2. Track a product with a target below its current price (no email yet).
3. In the **Tracked** tab press **Demo: simulate a price drop**. You get **one** email.
4. Press it again: no second email (spam protection).

The background monitor will later overwrite the fake price with the real one. That is expected.

## How alerts work
- `price <= target` and no alert sent yet → send one email, set `alert_sent = true`.
- Price goes back above target (or you change the target) → `alert_sent = false`, so a later drop alerts again.
- If the email fails, `alert_sent` stays false and the next check retries.
- A wrong SMTP password is reported once in the log; a blocked port 587 automatically retries over SSL (465).

## Multiple people
- Each product stores the email of the person who added it (`notify_email`); alerts go only there.
- The same product can be tracked by different people; one person can't track it twice (`unique (url, notify_email)`).
- Lists and CSV exports are filtered by email. One email can track at most `MAX_PRODUCTS_PER_EMAIL` products (default 5).

**Known limit (fine for a mini-project):** an email is an *address*, not a *login*. Someone who knows your
email and a product id could view or change that product. Real accounts would fix this.

## Where each Advanced Python concept is used (for the viva)
| Concept | Where |
|---|---|
| Abstraction, inheritance, polymorphism | `BaseScraper` (abstract) → 5 store scrapers; each overrides `parse`, `normalize_url`, `currency_for_url` |
| Encapsulation, classes, properties | `Product` (`from_row`, `to_dict`, `price_gap`, `currency`), `PriceChecker` |
| Decorators | `handle_errors` in `app.py`, `@property`, `@classmethod`, `@staticmethod`, `@lru_cache` |
| `lambda` | sort key in `list_products`, filter in `check_all_products` (`tracker_service.py`) |
| `map()` / `filter()` | `list_products` and `check_all_products` (`tracker_service.py`) |
| Generators | `iter_price_history` (`db.py`, pages through Supabase), `products_csv` / `history_csv` (`export_service.py`) |
| Custom exceptions | `exceptions.py` (`PriceNotFoundError`, …) |
| Exception handling | scraper network errors, SMTP errors, DB errors, `handle_errors` |
| Database CRUD | `database/db.py` (Supabase / PostgreSQL, parameterized by the client) |
| CSV | `services/export_service.py` |
| Threading | `services/monitor.py` (thread + `Event`), `_alert_lock` in `tracker_service.py` |
| Logging | `setup_logging()` in `app.py`, `logging.getLogger(__name__)` everywhere |
| Networking | `requests` in `base_scraper.py`, `smtplib` in `email_service.py` |
| Regular expressions | URL allow-lists in each scraper, `EMAIL_PATTERN`, currency detection in `currency.py` |
| Caching + thread safety | exchange-rate cache with a `threading.Lock` in `currency.py` |
| Security | host/path allow-list (SSRF), secrets in `.env`, narrow CORS, RLS on tables, HTML-escaped emails |

## Notes
- Login/registration is not included (optional in `context.md`).
- Timestamps are stored in UTC.
