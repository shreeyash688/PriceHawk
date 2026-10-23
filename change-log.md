Shreeyash - 20/10/26 - created filestructure , added context.md

Aryaman - 21/10/26 - updated file structure and finished the backend(api , health , services , models ,etc.), database connectivity is remaining 

Aryaman - 21/10/26 - Updated the backend further added the email sending and handeling for multiple recipents 

shreeyash-21/10/2026- upodated the HTML, CSS,JS file 

Antigravity - 23/10/26 - Fixed CSV history export data output bug; generated valid PNG extension icons; optimized Start Tracking with instant feedback and duplicate handling; resolved stale price display and race conditions; implemented inline target editing, pause/resume tracking, price history viewing with CSV export, and demo mode simulation; expanded automated test suite to 51 passing tests.

Divyansh - 23/10/26 - Cleanup + UI pass: alert emails now use the store's currency (₹ for Amazon.in/Flipkart/Myntra, was always £) with a new HTML email layout; currency + store returned by the API; added Supabase PostgreSQL schema.sql (replaces the old SQLite one); PUT /products is now all-or-nothing; wrong SMTP password no longer retried on port 465; Amazon URL check limited to real Amazon domains; removed unused config, empty content.js/background.js and duplicate icons. Redesigned the popup (store chip, quick 5/10/20% targets, gauge, toast messages visible on both tabs, list sorting, status badges, price-history chart, inline target edit, two-click remove) and fixed UI bugs (list could not scroll, double focus ring, hidden messages on Tracked tab, wrong £ in places, target editor overflow). Docs updated. 115 tests passing.

Divyansh - 23/10/26 - Rupees everywhere + Amazon blocking: all prices are converted to HOME_CURRENCY (INR) with live exchange rates (cached, offline fallback) and Amazon is asked for INR prices; the popup now reads Amazon's new split-price layout and hidden price fields, retries while the page loads, and sends the price it sees with the link (no server scrape needed); new POST /api/products/observe records prices read by the browser; Check now and the Tracked tab fall back to reading the page through the browser when Amazon blocks the server; "At your target" wording; Try again button. 129 tests passing.

Divyansh - 23/10/26 - Fixed "You're already tracking this product" appearing for NEW products: the full-list error (limit of 5) contained the words "already tracking" and the popup mistook it for a duplicate. Errors now carry a code ("duplicate", "limit_reached"); duplicate is checked before the limit; clear "Your list is full" message; default limit raised to 20 (MAX_PRODUCTS_PER_EMAIL in .env). 130 tests passing.

Divyansh - 23/10/26 - Backend version check (v0.4.0): the popup shows a "server out of date" pop-up when an old backend is still running (that old process was sending £ emails); startup log shows version + currency. Pop-up dialog when the tracking list is full (with "Manage tracked products"), red n/max badge when full. Monitor backs off from a store for BLOCKED_RETRY_MINUTES after a CAPTCHA; blocked products show a neutral note instead of "Check failed". 131 tests passing.
