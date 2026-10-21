-- Two small tables. "IF NOT EXISTS" lets us run this file on every start.

CREATE TABLE IF NOT EXISTS products (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT    NOT NULL,
    url              TEXT    NOT NULL UNIQUE,          -- UNIQUE = no duplicate products
    current_price    REAL    NOT NULL,
    target_price     REAL    NOT NULL CHECK (target_price > 0),
    tracking_active  INTEGER NOT NULL DEFAULT 1,       -- 1 = checking, 0 = paused
    alert_sent       INTEGER NOT NULL DEFAULT 0,       -- 1 = email already sent (stops spam)
    created_at       TEXT    NOT NULL,
    last_checked_at  TEXT,
    last_error       TEXT                              -- last scrape problem, if any
);

CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL,
    price       REAL    NOT NULL,
    checked_at  TEXT    NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_history_product ON price_history(product_id);
