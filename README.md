# PriceHawk 🦅
**Track Prices. Catch Deals. Save Money.**

A Chrome extension + Python (Flask) backend. The backend scrapes a product page, stores the price in SQLite,
re-checks it in a background thread, and emails you when the price reaches your target.
Supported site (v1): **books.toscrape.com** product pages.

## Backend setup
```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env         # Mac/Linux: cp .env.example .env   -> then fill in your email details
python app.py                  # API runs at http://127.0.0.1:5000
```
Run the tests (no internet or email needed): `cd backend && python -m unittest -v`

**Gmail:** turn on 2-Step Verification, create an *App Password*, and put it in `SMTP_PASSWORD` in `.env`.

## Folder map (backend/)
| File | Job |
|---|---|
| `app.py` | Flask routes, error-handling decorator, CORS, start-up |
| `config.py` | Settings from environment variables / `.env` |
| `exceptions.py` | Our custom errors (each knows its HTTP status code) |
| `scrapers/base_scraper.py` | Abstract `BaseScraper` (blueprint + shared download code) |
| `scrapers/books_scraper.py` | `BooksScraper`: URL validation + title/price parsing |
| `models/product.py` | `Product` class |
| `database/schema.sql`, `db.py` | Tables + all SQLite CRUD |
| `services/tracker_service.py` | `PriceChecker` + track / check / alert logic |
| `services/monitor.py` | Background thread |
| `services/email_service.py` | SMTP email |
| `services/export_service.py` | CSV export |
| `tests/` | Automated tests |

## API (for the extension)
All responses are JSON. Errors look like `{"error": "message"}` with status 400 (bad input), 404, 409 (already tracked), 502 (website problem).

| Method + URL | Body | What it does |
|---|---|---|
| `GET /api/health` | | Is the backend running? |
| `POST /api/preview` | `{"url"}` | Get title + price **without** saving (for the popup) |
| `POST /api/products` | `{"url", "target_price"}` | Start tracking (201) |
| `GET /api/products?sort=newest\|deals` | | List products (`deals` = closest to target first) |
| `GET /api/products/<id>` | | One product |
| `PUT /api/products/<id>` | `{"target_price"?, "tracking_active"?}` | Change target / pause / resume |
| `DELETE /api/products/<id>` | | Stop tracking and delete |
| `POST /api/products/<id>/check` | | "Check now" |
| `GET /api/products/<id>/history` | | Price history |
| `GET /api/export/products.csv` | | CSV of products |
| `GET /api/export/history.csv?product_id=` | | CSV of history (all, or one product) |
| `POST /api/products/<id>/simulate` | `{"price"}` | **Demo mode only**: fake a price |

**For whoever builds the extension:** add `"host_permissions": ["http://127.0.0.1:5000/*"]` to `manifest.json`,
and call the API from `popup.js` / `background.js` (not from the content script, which runs under the website's own origin).
To lock the API to your extension only, put its ID (from `chrome://extensions`) in `EXTENSION_ID` in `.env`.

## Demo (without waiting for a real price change)
1. In `.env`: `DEMO_MODE=true`, then start the server.
2. Track a book with a target of £40 (the real price is £51.77, so no email yet).
3. `curl -X POST http://127.0.0.1:5000/api/products/1/simulate -H "Content-Type: application/json" -d "{\"price\": 30}"`
4. You get **one** email. Repeat step 3 and no second email is sent (that is the spam protection).

Note: the background monitor will later overwrite the fake price with the real one. That is expected.

## How alerts work
`price <= target` and no alert sent yet → send one email, set `alert_sent = 1`.
Price goes back above target → `alert_sent = 0`, so a later drop alerts again.
If the email fails, `alert_sent` stays 0 and the next check retries.

## Where each Advanced Python concept is used (for the viva)
| Concept | Where |
|---|---|
| Abstraction, inheritance | `BaseScraper` (abstract) → `BooksScraper` |
| Encapsulation, classes | `Product` (`from_row`, `to_dict`, `price_gap`), `PriceChecker` |
| Decorator | `handle_errors` in `app.py` |
| `lambda` | sort key in `list_products` (`tracker_service.py`) |
| `map()` / `filter()` | `list_products` and `check_all_products` (`tracker_service.py`) |
| Generator | `iter_price_history` (`db.py`), `products_csv` / `history_csv` (`export_service.py`) |
| Custom exceptions | `exceptions.py` (`PriceNotFoundError`, ...) |
| Exception handling | scraper network errors, SMTP errors, DB errors, `handle_errors` |
| SQLite CRUD | `database/db.py` |
| CSV | `services/export_service.py` |
| Threading | `services/monitor.py` (thread + `Event`), `_alert_lock` in `tracker_service.py` |
| Logging | `setup_logging()` in `app.py`, `logging.getLogger(__name__)` everywhere |
| Networking | `requests` in `base_scraper.py`, `smtplib` in `email_service.py` |
| Security | host/path allow-list (SSRF), parameterized SQL, secrets in `.env`, narrow CORS |

## Notes
- Login/registration is not included (optional in `context.md`); `models/user.py` was therefore removed.
- Timestamps are stored in UTC.
