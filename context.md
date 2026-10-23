PriceHawk --- Project Context

> **Implementation status (23/10/26) — read this first.** The sections below are the original
> specification. The code has since grown past it in three deliberate ways:
> 1. **Database:** Supabase (PostgreSQL) instead of SQLite. Schema: `backend/database/schema.sql`;
>    CRUD: `backend/database/db.py`. Tests mock Supabase, so they still need no network.
> 2. **Stores:** Amazon, Flipkart, Myntra and eBay scrapers were added next to Books to Scrape.
>    Each keeps a strict host/path allow-list (SSRF protection).
> 3. **Currency:** decided per store from the URL (`currency_for_url`), e.g. ₹ for Amazon.in,
>    Flipkart, Myntra. Used in the API, the popup and the alert email.
>
> Where this file says "SQLite" or "Books to Scrape only", the points above take priority.

1. Project Overview
Project name: PriceHawk  
Tagline: Track Prices. Catch Deals. Save Money.  
Project type: Advanced Python Programming mini-project  
Product: A Chrome Extension connected to a Python backend  
Primary goal: Let users track product prices from their browser, set
a target price, and receive an email when the price reaches or falls
below that target.
PriceHawk is intended to be a working, locally testable project---not
only a visual prototype. The Chrome extension provides the user
interface, while the Python backend performs scraping, persistence,
price comparison, background monitoring, and email delivery.
The initial version will support Books to Scrape
(`books.toscrape.com`), a practice site intended for learning web
scraping. Support for other websites is a possible future enhancement,
not a requirement for the first working version.
2. Problem and Proposed Solution
Problem
People may want to know when a product becomes cheaper, but manually
revisiting product pages is inconvenient.
Proposed solution
PriceHawk allows a user to: 1. Open a supported product page in Chrome.
2. Click the PriceHawk extension icon. 3. Let the extension detect the
product title, URL, and price when possible. 4. Enter a target price and
start tracking. 5. Use manual URL entry if automatic detection is
unavailable. 6. Let the Python backend check the price periodically. 7.
Receive an email when the price is at or below the target. 8. Review
tracked products and recorded price history. 9. Export supported records
to CSV.
3. Scope
Essential first-version features
Chrome Extension using Manifest V3.
Popup interface with product information and target-price input.
Automatic product detection on supported pages where possible.
Manual product URL entry as a fallback.
Track multiple products.
Flask backend API.
Requests and BeautifulSoup scraper for Books to Scrape.
SQLite database and CRUD operations.
Background price monitoring using Python threading.
Price-history records.
SMTP email notifications.
CSV export.
Input validation, exception handling, and logging.
A controlled demonstration/test mode so an alert can be demonstrated
without waiting for a real price change.
Optional or future features
User registration and login.
Price-history charts.
Additional scraper implementations for other sites.
AI-based price advice or trend analysis.
Chrome Web Store publication.
Do not build optional features before the essential end-to-end workflow
works.
4. Technology Stack
---
Layer                   Technology              Responsibility
---
Browser extension       Chrome Extension        Extension structure and
Manifest V3             permissions
Popup interface         HTML and CSS            User interface
Popup interactions      JavaScript              Form handling and UI
updates
Browser background      JavaScript service      Extension lifecycle and
tasks                   worker                  background browser-side
tasks
Product-page            Content script and/or   Read product details
integration             supported-page DOM      where permitted
access
Backend                 Python + Flask          HTTP API and
application logic
HTTP scraping           Requests                Fetch supported product
pages
HTML parsing            BeautifulSoup           Extract title and price
Database                SQLite via Python       Persist products and
`sqlite3`               price history
Background monitoring   Python `threading`      Periodic price checks
Email                   `smtplib` and email     Send price-drop
utilities               notifications
Data export             Python `csv`            Export records
Configuration           Environment variables   Keep secrets and local
settings outside source
code
Logging                 Python `logging`        Record events and
errors
No React or Node.js backend is required for the first version. Keep the
stack simple and appropriate for an Advanced Python Programming course.
5. High-Level Architecture
``` text
User
 |
 v
Chrome Extension (Manifest V3)
 |-- popup.html / popup.css / popup.js
 |-- background.js (service worker)
 |-- content.js (if needed for supported-page detection)
 |
 | HTTP requests to local API
 v
Flask Backend
 |-- API routes and validation
 |-- Product tracking service
 |-- Scraper interface and implementation
 |-- Price checker
 |-- Email service
 |-- CSV export service
 |
 +------> Requests + BeautifulSoup
 |              |
 |              v
 |        Books to Scrape
 |
 +------> SQLite database
 |          |-- users (optional if authentication is added)
 |          |-- products
 |          |-- price_history
 |          |-- notification history (recommended if implemented)
 |
 +------> Background price-monitoring worker
                |
                v
         Compare current price with target
                |
          target reached?
             /       \
           yes        no
            |          |
            v          v
        Send email   Continue monitoring
```
The Chrome extension is the client. The Python backend owns the trusted
tracking logic, scraper, database, price comparisons, and SMTP
credentials.
6. Proposed Project Structure
``` text
PriceHawk/
├── extension/
│   ├── manifest.json
│   ├── popup.html
│   ├── popup.css
│   ├── popup.js
│   ├── background.js
│   ├── content.js
│   └── icons/
│       ├── icon16.png
│       ├── icon48.png
│       └── icon128.png
│
├── backend/
│   ├── app.py
│   ├── config.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base_scraper.py
│   │   └── books_scraper.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── product.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── tracker_service.py
│   │   ├── email_service.py
│   │   └── export_service.py
│   └── database/
│       ├── __init__.py
│       ├── db.py
│       └── schema.sql
│
├── tests/
│   ├── test_scraper.py
│   ├── test_database.py
│   └── test_price_checker.py
├── README.md
├── context.md
└── .gitignore
```
This is a proposed structure and can be simplified as development
progresses. Create actual icon image files; filenames alone are not
sufficient.
7. Main Functional Requirements
7.1 Extension popup
Show the detected product title and current price when available.
Show the current page URL.
Allow a target price to be entered.
Provide a Track Price action.
Display clear success and error messages.
Provide a manual URL-entry option.
Show tracking status and, if practical, a small list of tracked
products.
7.2 Product scraper
Initially accept only supported Books to Scrape product URLs.
Validate the URL and hostname before fetching it.
Use request timeouts and handle network failures.
Parse product title and price.
Raise a custom `PriceNotFoundError` when the expected price cannot
be extracted.
Avoid assuming every page has the same HTML structure.
Do not accept arbitrary URLs from the extension: validate on the
backend to reduce server-side request forgery (SSRF) risk.
7.3 Product tracking
Save product URL, title, current price, target price, tracking
status, and timestamps.
Allow users to track multiple products.
Avoid duplicate product entries where appropriate.
Support viewing, updating the target price, checking now, and
deleting a tracked product.
Record successful price checks in price history.
7.4 Background monitoring
Check active products on a configurable interval suitable for local
demonstration.
Keep monitoring work separate from individual Flask request
handlers.
Ensure the development server or reload mechanism does not
accidentally start multiple workers.
Handle thread safety when reading or writing SQLite data.
Use a separate database connection per thread or another safe
connection strategy.
Record network and parsing errors without crashing the entire
worker.
Prevent repeated email alerts for the same target-price event. Store
notification state or implement an equivalent deduplication
mechanism.
Include a manual Check Now option.
7.5 Email notifications
Send an email when the latest price is less than or equal to the
target price.
Include the product title, current price, target price, and product
URL.
Read SMTP settings and credentials from environment variables.
Never commit real passwords, app passwords, API keys, or `.env`
files.
Log delivery outcomes without logging secrets.
7.6 Database and exports
Use SQLite for the first version.
Support create, read, update, and delete operations for tracked
products.
Store historical price observations.
Export tracked products and/or price history to CSV.
Handle missing files, invalid values, database failures, and
permission errors.
8. Proposed Database Design
Keep the initial database small.
`products`
Suggested fields: - `id` --- primary key - `title` - `url` --- validated
supported product URL - `current_price` - `target_price` -
`tracking_active` - `created_at` - `last_checked_at`
If authentication is added, include `user_id` as a foreign key.
`price_history`
Suggested fields: - `id` --- primary key - `product_id` --- foreign
key - `price` - `checked_at`
`users` (optional)
Suggested fields: - `id` --- primary key - `email` --- unique -
`password_hash` - `created_at`
A notification-history table or notification-state fields are
recommended if needed to prevent repeated alerts and record whether an
email was sent.
Do not store plaintext passwords. Authentication is optional for the
first local demonstration unless required by the course.
9. Advanced Python Programming Concepts to Demonstrate
The project should clearly and meaningfully demonstrate the course
topics.
Object-oriented programming
`BaseScraper`: abstract base class defining the scraper interface.
`BooksScraper`: subclass implementing the supported website scraper.
`Product`: represents a tracked product.
`PriceChecker`: compares current and target prices.
Use inheritance, abstraction, encapsulation, and appropriate
methods.
Advanced functions and Python features
`@login_required` only if authentication is implemented; otherwise
use a relevant decorator only when it provides real value.
Use `lambda` for suitable small sorting keys or transformations.
Use `map()` and `filter()` for meaningful data-processing examples,
not just to tick a box.
Use a generator to read or process price-history records
incrementally where appropriate.
Files, exceptions, and database
SQLite CRUD.
CSV export using Python's `csv` module.
Custom `PriceNotFoundError`.
Exception handling for network, parsing, database, file, and SMTP
failures.
Logging with Python's `logging` module.
Threads and networking
HTTP requests to Books to Scrape.
SMTP email delivery.
Python background thread for periodic monitoring.
Clear separation between the Chrome extension's JavaScript service
worker and the backend's Python monitoring thread.
Document where each concept is implemented so it is easy to explain in
the viva.
10. Development Roadmap
Build and test in this order:
Create the repository and folder structure.
Add `manifest.json` and load a minimal extension in Chrome Developer
Mode.
Build the popup UI.
Detect the supported product page and provide manual URL entry.
Implement the `BaseScraper` and `BooksScraper` classes.
Build the Flask API and validate requests.
Create the SQLite schema and product CRUD operations.
Connect the popup to the Flask API.
Display real tracked-product data.
Add price history.
Add the background monitoring worker and manual check action.
Add SMTP email notifications and alert deduplication.
Add CSV export and logging.
Add controlled demonstration mode for reliable price-drop testing.
Test failure cases and prepare project documentation and viva notes.
Milestone 1: Chrome can load the extension, show the popup, and
accept a product URL and target price.  
Milestone 2: The extension can call Flask, and Flask can scrape and
save a supported product.  
Milestone 3: Background monitoring records price history and sends a
testable email alert.  
Final milestone: The complete workflow works reliably and can be
demonstrated end to end.
11. Testing Plan
Test at least these cases: - Valid supported product URL. - Invalid URL
or unsupported domain. - Product title or price cannot be found. -
Website timeout or unavailable connection. - Invalid or negative target
price. - SQLite insert, read, update, and delete. - Multiple tracked
products. - Price above target. - Price equal to target. - Price below
target. - Email success and SMTP failure. - No duplicate alert on every
polling cycle. - CSV export with records and with no records. -
Background worker does not multiply when the Flask development server
reloads. - Extension handles backend unavailable/CORS errors clearly. -
`.env` and secrets are not committed.
12. Security and Reliability Rules
Keep the backend limited to the supported practice domain at first.
Validate URLs server-side and allow only expected hosts and paths.
Use request timeouts and sensible polling intervals.
Do not expose SMTP credentials in extension JavaScript.
Keep secrets in environment variables and commit only `.env.example`
with placeholder values.
Use parameterized SQLite queries.
If login is implemented, hash passwords and protect user-specific
records.
Configure Flask CORS narrowly for the extension's required origin;
do not enable unrestricted access without a reason.
Do not claim support for every shopping site until individual
scrapers are implemented and tested.
Use a controlled test mode for demos rather than relying on a real
product price to change at a convenient time.
13. Git and Repository Practices
Keep `extension/` and `backend/` in the same repository.
Commit the project structure first, then commit each working
milestone separately.
Suggested commit messages:
`Initial PriceHawk project structure`
`Add Chrome extension popup`
`Implement Books to Scrape parser`
`Add Flask tracking API`
`Persist products and price history`
`Implement background price monitoring`
`Add email alerts and CSV export`
Use `.gitignore` to exclude `.env`, virtual environments,
`__pycache__/`, local databases if they contain user data, logs, and
generated exports.
Keep `README.md` for setup and usage instructions. Keep this
`context.md` as the detailed project specification and shared
reference for future development sessions.
Update`change-log.md`with your latest changes and updates to the directry with your name and date.
14. Project Success Criteria
The project is successful when: 1. The extension loads in Chrome
Developer Mode. 2. A user can track a supported product using automatic
detection or manual URL entry. 3. The Flask backend validates and
scrapes the product. 4. The product is stored in SQLite. 5. The
background worker records price observations. 6. The target-price
condition is detected correctly. 7. An email alert is sent without
repeatedly spamming the user. 8. Price history can be viewed and
exported to CSV. 9. Errors are handled and logged. 10. The student can
explain the architecture and demonstrate the Advanced Python Programming
concepts used.
15. Current Decisions and Open Items
Decisions already made
Project name: PriceHawk.
Deliverable: Chrome Extension + Python backend.
Initial scraping target: Books to Scrape.
Extension should support both automatic detection and manual URL
entry.
Backend: Flask.
Database: Supabase / PostgreSQL (originally SQLite).
Stores: Books to Scrape, Amazon, Flipkart, Myntra, eBay.
Currency: per store, from the URL (₹ for Indian stores).
Scraping: Requests + BeautifulSoup.
Monitoring: Python threading.
Alerts: SMTP email.
Export: CSV.
Build incrementally and test each milestone.
Items to decide during implementation
Final visual design and logo.
Exact API route names and request/response formats.
SMTP provider: Gmail with an App Password (SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD).
Whether login is required by the course.
Whether to add charts or additional websites after the core version
works.
16. One-Sentence Project Summary
PriceHawk is a Manifest V3 Chrome Extension connected to a Flask-based
Python backend that scrapes supported product pages, tracks prices in
SQLite, monitors target prices in a background thread, records price
history, exports data to CSV, and sends email alerts when a target price
is reached.