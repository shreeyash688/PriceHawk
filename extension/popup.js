"use strict";

// =====================================================
// CONFIG
// =====================================================

const API_BASE = "http://127.0.0.1:5000";

const API = {
  health: `${API_BASE}/api/health`,
  preview: `${API_BASE}/api/preview`,
  add: `${API_BASE}/api/products`,
  list: (email, sort = "newest") =>
    `${API_BASE}/api/products?email=${encodeURIComponent(email)}&sort=${encodeURIComponent(sort)}`,
  product: (id) => `${API_BASE}/api/products/${encodeURIComponent(id)}`,
  check: (id) => `${API_BASE}/api/products/${encodeURIComponent(id)}/check`,
  history: (id) => `${API_BASE}/api/products/${encodeURIComponent(id)}/history`,
  simulate: (id) => `${API_BASE}/api/products/${encodeURIComponent(id)}/simulate`,
  observe: `${API_BASE}/api/products/observe`,
  exportProducts: (email) => `${API_BASE}/api/export/products.csv?email=${encodeURIComponent(email)}`,
  exportHistory: (email, id) =>
    `${API_BASE}/api/export/history.csv?email=${encodeURIComponent(email)}` +
    (id ? `&product_id=${encodeURIComponent(id)}` : "")
};

// Same store list and currencies as the backend scrapers.
const AMAZON_RE = /^(?:www\.|m\.|smile\.)?amazon\.(com|in|co\.uk|ca|de|fr|es|it|nl|com\.au|co\.jp|ae|sa|sg|com\.br|com\.mx)$/i;
const EBAY_RE = /^(?:www\.|m\.)?ebay\.(com|co\.uk|ca|com\.au|de|fr|es|it|nl|ie|at|ch|be|pl)$/i;
const AMAZON_CURRENCY = {
  in: "₹", "co.uk": "£", de: "€", fr: "€", es: "€", it: "€", nl: "€", ca: "CA$", "com.au": "AU$",
  "co.jp": "¥", ae: "AED", sa: "SAR", sg: "S$", "com.br": "R$", "com.mx": "MX$", com: "$"
};
const EBAY_CURRENCY = {
  "co.uk": "£", de: "€", fr: "€", es: "€", it: "€", nl: "€", ie: "€", at: "€", be: "€",
  ch: "CHF", pl: "zł", ca: "CA$", "com.au": "AU$", com: "$"
};
const STORE_NAMES = "Amazon, Flipkart, Myntra, eBay or Books to Scrape";
const CURRENCY_SYMBOLS = {
  INR: "₹", USD: "$", GBP: "£", EUR: "€", CAD: "CA$", AUD: "AU$", JPY: "¥", AED: "AED", SAR: "SAR",
  SGD: "S$", BRL: "R$", MXN: "MX$", CHF: "CHF", PLN: "zł"
};
const currencySymbol = (code) => (code ? CURRENCY_SYMBOLS[String(code).toUpperCase()] || code : null);

/** { name, currency } for a supported product URL, otherwise null. */
function storeInfo(url) {
  let host;
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return null;
  }
  let m;
  if (host === "books.toscrape.com") return { name: "Books to Scrape", currency: "£" };
  if ((m = host.match(AMAZON_RE))) return { name: `Amazon.${m[1]}`, currency: AMAZON_CURRENCY[m[1]] || "$" };
  if (/(^|\.)flipkart\.com$/.test(host)) return { name: "Flipkart", currency: "₹" };
  if (/(^|\.)myntra\.com$/.test(host)) return { name: "Myntra", currency: "₹" };
  if ((m = host.match(EBAY_RE))) return { name: `eBay.${m[1]}`, currency: EBAY_CURRENCY[m[1]] || "$" };
  return null;
}

// =====================================================
// STATE + SMALL HELPERS
// =====================================================

const $ = (id) => document.getElementById(id);

let detected = null; // { title, price, currency, url, store }
let demoMode = false;
let listRequestId = 0;
let submitting = false;
let sortMode = readStored("pricehawk_sort") || "newest";
let toastTimer = null;
let homeSymbol = "₹"; // every price is shown in the backend's home currency (INR by default)

function readStored(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function writeStored(key, value) {
  try { localStorage.setItem(key, value); } catch { /* storage unavailable: not critical */ }
}

/** 1499 -> "₹1,499.00" (Indian digit grouping for rupees). */
function money(value, currency) {
  const n = Number(value);
  if (value === null || value === undefined || value === "" || !Number.isFinite(n)) return "—";
  const locale = currency === "₹" ? "en-IN" : "en-US";
  return `${currency || ""}${n.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function timeAgo(iso) {
  if (!iso) return "Not checked yet";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  const s = Math.max(0, (Date.now() - then.getTime()) / 1000);
  if (s < 60) return "Checked just now";
  if (s < 3600) return `Checked ${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `Checked ${Math.floor(s / 3600)} h ago`;
  return `Checked ${then.toLocaleDateString(undefined, { day: "numeric", month: "short" })}`;
}

function shortDate(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso || "");
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

const EMAIL_PATTERN = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/;
const getEmail = () => $("email").value.trim();
const isValidEmail = (email = getEmail()) => email.length <= 254 && EMAIL_PATTERN.test(email);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** Inline SVG icons (paths only; styling comes from CSS). */
const ICONS = {
  refresh: '<path d="M20 11a8 8 0 10-2.3 5.7M20 5v6h-6"/>',
  pause: '<path d="M9 6v12M15 6v12"/>',
  play: '<path d="M8 5l11 7-11 7z"/>',
  chart: '<path d="M4 19h16M6 15l4-5 3 3 5-7"/>',
  pencil: '<path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4"/>',
  check: '<path d="M5 12l5 5 9-10"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  bolt: '<path d="M13 3L5 14h6l-1 7 8-11h-6z"/>'
};
const icon = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;

// =====================================================
// TOAST (shared by both tabs)
// =====================================================

function say(message, kind = "info") {
  const box = $("alert");
  clearTimeout(toastTimer);
  if (!message) {
    box.classList.add("hidden");
    return;
  }
  box.dataset.variant = kind;
  $("alertText").textContent = message;
  box.classList.remove("hidden");
  // errors stay longer; everything disappears on its own
  toastTimer = setTimeout(() => box.classList.add("hidden"), kind === "err" ? 8000 : 4000);
}
$("alertClose").addEventListener("click", () => say(""));

// =====================================================
// BACKEND
// =====================================================

async function api(url, options = {}) {
  let response;
  try {
    response = await fetch(url, {
      ...options,
      headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers }
    });
  } catch {
    setConnection(false);
    throw new Error("Can't reach the PriceHawk backend. Start it with: python app.py");
  }
  const isJson = (response.headers.get("content-type") || "").includes("application/json");
  const data = isJson ? await response.json().catch(() => ({})) : await response.text().catch(() => "");
  if (!response.ok) {
    const error = new Error((data && data.error) || `Request failed (${response.status})`);
    error.status = response.status;
    error.code = data && data.code; // "duplicate", "limit_reached", "invalid", ...
    throw error;
  }
  return data;
}

function setConnection(ok) {
  $("conn").dataset.state = ok ? "ok" : "err";
  $("connText").textContent = ok ? (demoMode ? "Connected · demo mode" : "Connected") : "Backend offline";
}

async function checkBackend() {
  try {
    const data = await api(API.health);
    demoMode = Boolean(data.demo_mode);
    homeSymbol = data.currency_symbol || homeSymbol;
    $("targetCurrencyAddon").textContent = homeSymbol;
    setConnection(true);
    return true;
  } catch (error) {
    say(error.message, "err");
    return false;
  }
}

// =====================================================
// TABS
// =====================================================

function show(view) {
  document.querySelectorAll(".tab").forEach((tab) => {
    const active = tab.dataset.view === view;
    tab.dataset.state = active ? "active" : "inactive";
    tab.setAttribute("aria-selected", String(active));
  });
  $("view-track").classList.toggle("hidden", view !== "track");
  $("view-list").classList.toggle("hidden", view !== "list");
  if (view === "list") loadList();
}
document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => show(tab.dataset.view)));

// =====================================================
// PRODUCT DETECTION
// =====================================================

/**
 * Reads { title, price, currency } from a product page.
 *  - extractProduct(null, null) is injected into the open tab and reads the live page.
 *  - extractProduct(html, url) runs in the popup on HTML fetched by the browser.
 * chrome.scripting copies only this function into the page, so it must be self-contained.
 */
function extractProduct(html, pageUrl) {
  const doc = html ? new DOMParser().parseFromString(html, "text/html") : document;
  const url = pageUrl || location.href;
  let host = "";
  try { host = new URL(url).hostname.toLowerCase(); } catch { /* keep "" */ }
  const q = (selector) => doc.querySelector(selector);
  const clean = (value) => String(value ?? "").replace(/\s+/g, " ").trim();
  const textOf = (node) => (node ? clean(node.getAttribute("content") ?? node.getAttribute("value") ?? node.textContent) : "");

  // Bot-check pages have no product at all.
  if (q("#captchacharacters, form[action*='validateCaptcha']") ||
      /enter the characters you see below|type the characters you see in this image|robot or human\?/i
        .test(clean(doc.body?.textContent).slice(0, 3000))) {
    return { blocked: true, title: null, price: null, currency: null, url };
  }

  const CURRENCIES = [
    [/\bINR\b|₹|\bRs\.?\s?(?=\d)/i, "INR"], [/\bUSD\b|US\$/, "USD"], [/\bCAD\b|CA\$|C\$/, "CAD"],
    [/\bAUD\b|AU\$|A\$/, "AUD"], [/\bSGD\b|S\$/, "SGD"], [/\bBRL\b|R\$/, "BRL"], [/\bMXN\b|MX\$/, "MXN"],
    [/\bGBP\b|£/, "GBP"], [/\bEUR\b|€/, "EUR"], [/\bJPY\b|¥|￥/, "JPY"], [/\bAED\b/, "AED"],
    [/\bSAR\b/, "SAR"], [/\bCHF\b/, "CHF"], [/\bPLN\b|zł/, "PLN"], [/\$/, "USD"]
  ];
  const currencyOf = (text) => (CURRENCIES.find(([re]) => re.test(String(text || ""))) || [])[1] || null;

  // "₹45,999.00" / "INR 45,999" / "1.299,00 €" / "$1,299.99$1,299.99" -> number
  const num = (value) => {
    const match = String(value ?? "").replace(/ /g, " ").match(/\d[\d.,\s]*/);
    if (!match) return null;
    let s = match[0].replace(/\s/g, "").replace(/[.,]+$/, "");
    const comma = s.lastIndexOf(","), dot = s.lastIndexOf(".");
    s = comma > dot && s.length - comma - 1 === 2 ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
    const n = parseFloat(s);
    return Number.isFinite(n) && n > 0 ? Math.round(n * 100) / 100 : null;
  };

  let title = null;
  let price = null;
  let currency = null;
  const found = (amount, code) => {
    if (price !== null || amount === null) return price !== null;
    price = amount;
    currency = code || currency;
    return true;
  };

  // 1. Structured data (Flipkart, Myntra, eBay and many others publish it)
  for (const script of doc.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const json = JSON.parse(script.textContent || "null");
      const items = [].concat(json || []).flatMap((x) => (x && x["@graph"]) || [x]);
      for (const item of items) {
        const type = [].concat(item?.["@type"] || []);
        if (!type.some((t) => /product/i.test(t))) continue;
        title = title || clean(item.name) || null;
        const offers = item.offers;
        const offer = Array.isArray(offers) ? offers[0] : Array.isArray(offers?.offers) ? offers.offers[0] : offers;
        found(num(offer?.price ?? offer?.lowPrice), currencyOf(offer?.priceCurrency));
      }
    } catch { /* broken JSON-LD: try the page instead */ }
  }

  // 2. Store-specific layouts
  if (host.includes("amazon.")) {
    title = clean(q("#productTitle")?.textContent) || clean(q("#title")?.textContent) || title;

    // a) hidden buy-box fields (present even when the visible price is drawn in pieces)
    found(num(q('input[name="items[0.base][customerVisiblePrice][amount]"]')?.value),
      currencyOf(q('input[name="items[0.base][customerVisiblePrice][currencyCode]"]')?.value));

    // b) the main price block: screen-reader text, or "whole" + "fraction" pieces
    const boxes = ["#corePriceDisplay_desktop_feature_div", "#corePrice_desktop", "#corePrice_feature_div",
      "#apex_desktop", "#apex_offerDisplay_desktop", "#tp_price_block_total_price_ww", "#buybox",
      "#desktop_buybox", "#price", "#centerCol", "#ppd"];
    for (const selector of boxes) {
      const box = q(selector);
      if (!box || price !== null) continue;
      for (const node of box.querySelectorAll(".priceToPay .a-offscreen, .a-price:not(.a-text-price) .a-offscreen")) {
        const text = clean(node.textContent);
        if (found(num(text), currencyOf(text))) break;
      }
      const whole = box.querySelector(".priceToPay .a-price-whole, .a-price:not(.a-text-price) .a-price-whole");
      if (price === null && whole) {
        const block = whole.closest(".a-price") || box;
        const digits = clean(whole.textContent).replace(/\D/g, "");
        const cents = clean(block.querySelector(".a-price-fraction")?.textContent).replace(/\D/g, "") || "00";
        found(num(`${digits}.${cents}`), currencyOf(block.querySelector(".a-price-symbol")?.textContent));
      }
    }

    // c) older layouts
    for (const selector of ["#priceblock_dealprice", "#priceblock_ourprice", "#priceblock_saleprice",
      "#price_inside_buybox", "#newBuyBoxPrice", "#kindle-price", "#sns-base-price"]) {
      const text = textOf(q(selector));
      if (found(num(text), currencyOf(text))) break;
    }
    found(num(q("#twister-plus-price-data-price")?.value), null);
    currency = currency || currencyOf(q(".a-price-symbol")?.textContent);
  } else if (host === "books.toscrape.com") {
    title = title || clean(q(".product_main h1")?.textContent) || null;
    const text = textOf(q(".product_main .price_color"));
    found(num(text), currencyOf(text) || "GBP");
  } else if (host.includes("flipkart.com")) {
    title = title || clean(q("span.VU-ZEz, span.B_NuCI, h1.yhB1nd span, h1")?.textContent) || null;
    const text = textOf(q("div.Nx9bqj.CxhGGd, div._30jeq3._16Jk6d, div.Nx9bqj, div._30jeq3"));
    found(num(text), "INR");
  } else if (host.includes("myntra.com")) {
    const myx = [...doc.scripts].map((s) => s.textContent).find((t) => t.includes("pdpData"));
    try {
      const pdp = JSON.parse(myx.match(/window\.__myx\s*=\s*(\{.*\})\s*;?\s*$/s)[1]).pdpData;
      title = title || clean(`${pdp.brand?.name || pdp.brand || ""} ${pdp.name || ""}`) || null;
      found(num(pdp.price?.discounted ?? pdp.price?.mrp), "INR");
    } catch { /* not on this page */ }
    title = title || clean(`${q("h1.pdp-title")?.textContent || ""} ${q("h1.pdp-name")?.textContent || ""}`) || null;
    found(num(textOf(q("span.pdp-price strong, span.pdp-price"))), "INR");
  } else if (host.includes("ebay.")) {
    title = title || clean(q("h1.x-item-title__mainTitle span, h1#itemTitle")?.textContent).replace(/^details about\s+/i, "") || null;
    const text = textOf(q("div.x-price-primary span.ux-textspans, span#prcIsum, span#mm-saleDscPrc"));
    found(num(text), currencyOf(text));
  }

  // 3. Generic page metadata
  const metaPrice = q('meta[property="product:price:amount"], meta[property="og:price:amount"], [itemprop="price"]');
  const metaCurrency = q('meta[property="product:price:currency"], meta[property="og:price:currency"], [itemprop="priceCurrency"]');
  found(num(textOf(metaPrice)), currencyOf(textOf(metaCurrency)));
  title = title || clean(q('meta[property="og:title"]')?.getAttribute("content")) || clean(q("h1")?.textContent) || null;

  return { blocked: false, title: title ? title.slice(0, 500) : null, price, currency, url };
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const hasProduct = (page) => Boolean(page && !page.blocked && page.title && Number.isFinite(page.price));
const pageData = (page) => ({ title: page.title, price: page.price, currency: page.currency || undefined });

/** Read a tab, retrying while the page is still loading its price. */
async function readTab(tabId, attempts = 4) {
  let last = null;
  for (let i = 0; i < attempts; i++) {
    try {
      const [result] = await chrome.scripting.executeScript({ target: { tabId }, func: extractProduct, args: [null, null] });
      last = result?.result || null;
      if (hasProduct(last) || last?.blocked) return last;
    } catch (error) {
      console.warn("PriceHawk: could not read the tab", error);
      return null; // e.g. chrome:// pages or no permission: retrying won't help
    }
    await sleep(700);
  }
  return last;
}

/** Fetch a product page with the user's own browser and read it (servers get blocked, browsers rarely do). */
async function fetchAndExtract(url) {
  try {
    const response = await fetch(url, { credentials: "include" });
    if (!response.ok) return null;
    const page = extractProduct(await response.text(), url);
    return hasProduct(page) ? page : null;
  } catch {
    return null;
  }
}

/** Last resort: open the page in a hidden background tab, read it, close it. */
async function readInBackgroundTab(url) {
  let tab;
  try {
    tab = await chrome.tabs.create({ url, active: false });
    await new Promise((resolve) => {
      const done = () => {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      };
      const listener = (id, info) => { if (id === tab.id && info.status === "complete") done(); };
      const timer = setTimeout(done, 20000);
      chrome.tabs.onUpdated.addListener(listener);
    });
    const page = await readTab(tab.id, 3);
    return hasProduct(page) ? page : null;
  } catch {
    return null;
  } finally {
    if (tab?.id) chrome.tabs.remove(tab.id).catch(() => {});
  }
}

/** Read a product page through the browser: quick fetch first, then a hidden tab. */
async function readInBrowser(url, { allowTab = true } = {}) {
  return (await fetchAndExtract(url)) || (allowTab ? await readInBackgroundTab(url) : null);
}

const looksBlocked = (message) =>
  /anti-bot|captcha|verification|access restriction|took too long|could not load|blocked/i.test(message || "");

function setDetectStatus(label, tone) {
  $("detectText").textContent = label;
  $("detectStatus").dataset.tone = tone;
}

function showProduct(product) {
  detected = product;
  $("productCard").dataset.state = "ok";
  $("pStore").textContent = product.store || "Product";
  $("pStore").classList.remove("hidden");
  $("pTitle").textContent = product.title;
  $("pHint").classList.add("hidden");
  $("retryBtn").classList.add("hidden");
  $("pPrice").textContent = money(product.price, product.currency);
  $("pOriginal").textContent = product.original ? `converted from ${product.original}` : "";
  $("pOriginal").classList.toggle("hidden", !product.original);
  $("pUrl").textContent = product.url;
  $("pUrl").href = product.url;
  $("pUrl").classList.remove("hidden");
  $("targetCurrencyAddon").textContent = product.currency;
  $("target").placeholder = suggestedTarget(10)?.toFixed(2) || "0.00";
  updateGauge();
}

function showNoProduct(title, hint, statusLabel, tone, canRetry = false) {
  detected = null;
  $("productCard").dataset.state = "empty";
  $("pStore").classList.add("hidden");
  $("pTitle").textContent = title;
  $("pHint").textContent = hint;
  $("pHint").classList.toggle("hidden", !hint);
  $("retryBtn").classList.toggle("hidden", !canRetry);
  $("pUrl").classList.add("hidden");
  $("target").placeholder = "0.00";
  setDetectStatus(statusLabel, tone);
  updateGauge();
}

/** Turn a /api/preview answer into the popup's product object. */
function fromPreview(data, store, page) {
  return {
    title: data.title,
    price: data.price,
    currency: data.currency,
    url: data.url,
    store: store?.name,
    page,
    original: data.converted ? money(data.original_price, data.original_currency) : null
  };
}

async function detect() {
  $("productCard").dataset.state = "loading";
  setDetectStatus("Reading page…", "loading");

  let tab;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch { /* opened outside the extension */ }

  const store = tab?.url ? storeInfo(tab.url) : null;
  $("manualToggle").classList.toggle("hidden", !store); // no page product: the link box is the only option
  if (!store) {
    showNoProduct("Open a product page to start",
      `Works on ${STORE_NAMES}. You can also paste a link below.`, "No product", "muted");
    setManualOpen(true);
    return;
  }

  // 1. Read the page the user is looking at (retries while it is still loading)
  const page = await readTab(tab.id);

  if (hasProduct(page)) {
    // 2. Backend checks the link and converts the price to ₹
    try {
      const data = await api(API.preview, {
        method: "POST",
        body: JSON.stringify({ url: tab.url, page: pageData(page) })
      });
      showProduct(fromPreview(data, store, pageData(page)));
      setDetectStatus("Detected", "green");
      reportTrackedPrice(data.url, pageData(page));
    } catch (error) {
      if (/supported stores|not an? .*product page|valid .*url/i.test(error.message)) {
        showNoProduct("This isn't a product page", `Open a single product on ${store.name} and click PriceHawk again.`, "No product", "muted");
      } else {
        // backend offline: still show what the page says, in the page's own currency
        showProduct({ ...pageData(page), url: tab.url, store: store.name, page: pageData(page),
          currency: currencySymbol(page.currency) || store.currency });
        setDetectStatus("Detected", "green");
      }
    }
    return;
  }

  // 3. Page unreadable (unusual layout): let the backend try the link itself
  try {
    const data = await api(API.preview, { method: "POST", body: JSON.stringify({ url: tab.url }) });
    showProduct(fromPreview(data, store, null));
    setDetectStatus("Detected", "green");
  } catch (error) {
    const reason = page?.blocked
      ? `${store.name} is showing a "robot check" in this tab. Solve it, then click Try again.`
      : looksBlocked(error.message)
        ? `${store.name} blocked the server, and the price on this page wasn't visible yet. Wait for the page to finish loading, then click Try again.`
        : error.message;
    showNoProduct("Couldn't read this product", reason, "Not found", "amber", true);
  }
}

/** If this email already tracks the open product, save the price the browser sees right now. */
async function reportTrackedPrice(url, page) {
  if (!isValidEmail()) return;
  try {
    const product = await api(API.observe, {
      method: "POST",
      body: JSON.stringify({ url, email: getEmail(), page })
    });
    setDetectStatus(product.alert_sent ? "Target reached" : "Tracking", "green");
  } catch { /* not tracked by this email: nothing to do */ }
}

// =====================================================
// TARGET GAUGE + QUICK TARGETS
// =====================================================

function suggestedTarget(percentOff) {
  if (!detected) return null;
  const value = detected.price * (1 - percentOff / 100);
  return detected.price >= 100 ? Math.floor(value) : Math.round(value * 100) / 100;
}

function updateGauge() {
  const target = parseFloat($("target").value);
  const price = detected?.price;
  const fill = $("gaugeFill");
  const label = $("gaugeText");
  document.querySelectorAll(".chip").forEach((chip) => { chip.disabled = !detected; });

  if (!Number.isFinite(price) || !Number.isFinite(target) || target <= 0) {
    fill.style.width = "0%";
    fill.classList.remove("hit");
    label.classList.remove("hit");
    label.textContent = detected ? "Set a target price below" : "";
    return;
  }

  const reached = price <= target;
  fill.style.width = `${Math.min(100, (target / price) * 100)}%`;
  fill.classList.toggle("hit", reached);
  label.classList.toggle("hit", reached);
  label.textContent = reached
    ? "Already at or below your target — you'll get an email right away"
    : `${money(price - target, detected.currency)} to go · needs a ${Math.round(((price - target) / price) * 100)}% drop`;
}

$("target").addEventListener("input", updateGauge);
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    const value = suggestedTarget(Number(chip.dataset.off));
    if (value === null) return;
    $("target").value = value.toFixed(2);
    updateGauge();
  });
});

// =====================================================
// MANUAL LINK
// =====================================================

function setManualOpen(open) {
  $("manualField").classList.toggle("hidden", !open);
  $("manualToggle").setAttribute("aria-expanded", String(open));
  $("manualToggle").textContent = open ? "Use the product on this page" : "Paste a product link instead";
}

$("retryBtn").addEventListener("click", () => detect());

$("manualToggle").addEventListener("click", () => {
  const open = $("manualField").classList.contains("hidden");
  setManualOpen(open);
  if (open) {
    $("manualUrl").focus();
  } else {
    $("manualUrl").value = "";
    detect();
  }
});

/** Quick client-side check so obvious mistakes don't need a server round trip. */
function validateProductUrl(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error("Enter a full product link starting with https://");
  }
  if (!storeInfo(parsed.href)) throw new Error(`Supported stores: ${STORE_NAMES}.`);
  return parsed.href;
}

async function previewManual() {
  const button = $("previewBtn");
  try {
    const url = validateProductUrl($("manualUrl").value.trim());
    button.disabled = true;
    button.textContent = "Checking…";
    setDetectStatus("Checking…", "loading");
    const data = await api(API.preview, {
      method: "POST",
      body: JSON.stringify({ url, email: isValidEmail() ? getEmail() : undefined })
    });
    showProduct(fromPreview(data, storeInfo(data.url) || storeInfo(url), null));
    setDetectStatus(data.already_tracked ? "Already tracked" : "Verified", data.already_tracked ? "amber" : "green");
    say(data.already_tracked ? "You're already tracking this product." : "Product found. Set a target and start tracking.", "ok");
  } catch (error) {
    setDetectStatus("Not found", "amber");
    say(looksBlocked(error.message)
      ? "The store blocked the server. Open the product page in this tab and click PriceHawk there instead."
      : error.message, "err");
  } finally {
    button.disabled = false;
    button.textContent = "Preview";
  }
}
$("previewBtn").addEventListener("click", previewManual);
$("manualUrl").addEventListener("keydown", (event) => { if (event.key === "Enter") previewManual(); });

// =====================================================
// START TRACKING
// =====================================================

function setTrackLoading(loading) {
  $("trackBtn").disabled = loading;
  $("trackSpin").classList.toggle("hidden", !loading);
  $("trackBtnText").textContent = loading ? "Adding…" : "Start tracking";
}

$("trackBtn").addEventListener("click", async () => {
  if (submitting) return;
  const manual = !$("manualField").classList.contains("hidden");
  const target = parseFloat($("target").value);
  const email = getEmail();
  let url;
  let page;

  try {
    if (manual && $("manualUrl").value.trim()) {
      url = validateProductUrl($("manualUrl").value.trim());
      if (detected?.url === url) page = detected.page || undefined;
    } else if (detected?.url) {
      url = detected.url;
      page = detected.page || undefined; // the price the user can see: no server scrape needed
    } else {
      throw new Error("No product yet. Open a product page or paste a link.");
    }
    if (!Number.isFinite(target) || target <= 0) throw new Error("Enter a target price greater than 0.");
    if (!isValidEmail(email)) throw new Error("Enter the email address where alerts should go.");
  } catch (error) {
    say(error.message, "err");
    return;
  }

  submitting = true;
  setTrackLoading(true);
  try {
    writeStored("pricehawk_email", email);
    const product = await api(API.add, {
      method: "POST",
      body: JSON.stringify({ url, target_price: target, email, page })
    });
    const currency = product.currency || detected?.currency;
    setDetectStatus("Tracking", "green");
    say(product.alert_sent
      ? `Already below your target! Alert sent to ${email}.`
      : `Tracking started. We'll email ${email} when it drops to ${money(target, currency)}.`, "ok");
    refreshCount();
  } catch (error) {
    if (error.code === "duplicate" || error.status === 409) {
      setDetectStatus("Already tracked", "amber");
      say("You're already tracking this product. Change its target in the Tracked tab.", "info");
    } else if (error.code === "limit_reached") {
      say(error.message, "err");
    } else {
      say(looksBlocked(error.message)
        ? "The store blocked the server. Open the product page in this tab and click PriceHawk there to track it."
        : error.message, "err");
    }
  } finally {
    submitting = false;
    setTrackLoading(false);
  }
});

// =====================================================
// TRACKED LIST
// =====================================================

function setEmptyState(title, description) {
  $("items").replaceChildren();
  $("empty").querySelector(".empty-title").textContent = title;
  $("empty").querySelector(".empty-desc").textContent = description;
  $("empty").classList.remove("hidden");
}

async function loadList() {
  const requestId = ++listRequestId;
  const email = getEmail();
  if (!isValidEmail(email)) {
    $("count").textContent = "0";
    setEmptyState("Add your email first", "Enter your alert email on the Track tab to see your products.");
    return;
  }
  try {
    const data = await api(API.list(email, sortMode));
    if (requestId !== listRequestId) return; // a newer request already answered
    const products = Array.isArray(data.products) ? data.products : [];
    $("count").textContent = String(products.length);
    if (products.length === 0) {
      setEmptyState("Nothing tracked yet", "Track a product and it will show up here.");
      return;
    }
    $("empty").classList.add("hidden");
    $("items").replaceChildren(...products.map(createCard));
    refreshBlockedInBrowser(products, requestId);
  } catch (error) {
    if (requestId !== listRequestId) return;
    setEmptyState("Couldn't load your products", error.message);
  }
}

/**
 * Products whose last SERVER check was blocked (CAPTCHA etc.) are re-read with the user's
 * browser, quietly, one by one. The backend records the price and sends alerts as usual.
 */
async function refreshBlockedInBrowser(products, requestId) {
  const blocked = products.filter((p) => p.tracking_active && looksBlocked(p.last_error));
  let updated = 0;
  for (const product of blocked) {
    if (requestId !== listRequestId) return; // list was reloaded meanwhile
    const page = await readInBrowser(product.url, { allowTab: false });
    if (!page) continue;
    try {
      const fresh = await api(API.observe, {
        method: "POST",
        body: JSON.stringify({ url: product.url, email: getEmail(), page: pageData(page) })
      });
      document.querySelector(`.item[data-id="${product.id}"]`)?.refresh(fresh);
      updated++;
    } catch { /* leave the card as it is */ }
  }
  if (updated) say(`Updated ${updated} price${updated > 1 ? "s" : ""} through your browser (the store blocked the server).`, "ok");
}

async function refreshCount() {
  if (!isValidEmail()) {
    $("count").textContent = "0";
    return;
  }
  try {
    const data = await api(API.list(getEmail()));
    $("count").textContent = String((data.products || []).length);
  } catch { /* the header already shows the backend is offline */ }
}

$("refreshListBtn").addEventListener("click", async () => {
  const button = $("refreshListBtn");
  button.disabled = true;
  button.classList.add("spinning");
  await loadList();
  button.disabled = false;
  button.classList.remove("spinning");
});

document.querySelectorAll("[data-sort]").forEach((button) => {
  const active = button.dataset.sort === sortMode;
  button.dataset.state = active ? "active" : "inactive";
  button.setAttribute("aria-checked", String(active));
  button.addEventListener("click", () => {
    sortMode = button.dataset.sort;
    writeStored("pricehawk_sort", sortMode);
    document.querySelectorAll("[data-sort]").forEach((b) => {
      b.dataset.state = b === button ? "active" : "inactive";
      b.setAttribute("aria-checked", String(b === button));
    });
    loadList();
  });
});

// =====================================================
// ONE TRACKED PRODUCT CARD
// =====================================================

function statusOf(p) {
  const hit = Number(p.current_price) <= Number(p.target_price);
  if (!p.tracking_active) return { key: "paused", label: "Paused", tone: "muted" };
  if (hit) return { key: "hit", label: p.alert_sent ? "Alert sent" : "Target reached", tone: "green" };
  if (p.last_error) return { key: "error", label: "Check failed", tone: "red" };
  return { key: "watching", label: "Watching", tone: "amber" };
}

function createCard(product) {
  const store = storeInfo(product.url);
  const currency = product.currency || homeSymbol;
  const item = el("li", "item");
  item.dataset.id = String(product.id);

  item.innerHTML = `
    <div class="item-top">
      <span class="store"></span>
      <span class="pill status"><span class="dot"></span><span class="status-text"></span></span>
    </div>
    <a class="item-title" target="_blank" rel="noopener noreferrer" title="Open product page"></a>
    <div class="item-prices">
      <div><span class="label">Now</span><strong class="now"></strong></div>
      <div>
        <span class="label">Target</span>
        <div class="target-view">
          <strong class="target-val"></strong>
          <button class="edit-btn" data-a="edit" type="button" title="Change target" aria-label="Change target">${icon("pencil")}</button>
        </div>
        <div class="target-edit hidden">
          <div class="input-group"><span class="input-addon"></span><input type="number" min="0.01" step="0.01" aria-label="New target price"></div>
          <button class="edit-btn" data-a="save" type="button" title="Save" aria-label="Save target">${icon("check")}</button>
          <button class="edit-btn" data-a="cancel" type="button" title="Cancel" aria-label="Cancel">${icon("x")}</button>
        </div>
      </div>
    </div>
    <div class="progress"><i></i></div>
    <div class="item-meta"><span class="gap-text"></span><span class="checked"></span></div>
    <p class="item-error hidden"></p>
    <div class="item-actions">
      <button class="btn" data-variant="outline" data-size="sm" data-a="check" type="button">${icon("refresh")}<span>Check now</span></button>
      <button class="btn" data-variant="outline" data-size="sm" data-a="pause" type="button"></button>
      <button class="btn" data-variant="outline" data-size="sm" data-a="history" type="button" aria-expanded="false">${icon("chart")}<span>History</span></button>
      <span class="spacer"></span>
      <button class="btn" data-variant="ghost" data-size="icon" data-a="remove" type="button" title="Remove" aria-label="Remove product">${icon("trash")}</button>
    </div>
    ${demoMode ? `<button class="btn demo-btn" data-variant="outline" data-size="sm" data-a="demo" type="button" title="Demo mode: pretend the price dropped below your target">${icon("bolt")}<span>Demo: simulate a price drop</span></button>` : ""}
    <div class="history hidden"></div>
  `;

  const q = (selector) => item.querySelector(selector);
  q(".store").textContent = store?.name || product.retailer || "Store";
  q(".item-title").textContent = product.title || "Untitled product";
  q(".item-title").href = product.url;
  q(".target-edit .input-addon").textContent = currency;

  // ---- redraw everything that depends on the product's data ----
  function render() {
    const status = statusOf(product);
    const now = Number(product.current_price);
    const target = Number(product.target_price);
    item.dataset.status = status.key;
    q(".status").dataset.tone = status.tone;
    q(".status-text").textContent = status.label;
    q(".now").textContent = money(now, currency);
    q(".target-val").textContent = money(target, currency);

    const fill = q(".progress i");
    fill.style.width = `${Math.min(100, (target / now) * 100) || 0}%`;
    fill.classList.toggle("hit", now <= target);

    const gap = q(".gap-text");
    gap.classList.toggle("hit", now <= target);
    gap.textContent = now === target
      ? "At your target"
      : now < target
        ? `${money(target - now, currency)} below target`
        : `${money(now - target, currency)} to go`;
    q(".checked").textContent = timeAgo(product.last_checked_at);

    q(".item-error").textContent = !product.last_error ? ""
      : looksBlocked(product.last_error)
        ? `${store?.name || "The store"} blocked the last server check. Press Check now to read the price through your browser.`
        : `Last check failed: ${product.last_error}`;
    q(".item-error").classList.toggle("hidden", !product.last_error);

    q('[data-a="pause"]').innerHTML = product.tracking_active
      ? `${icon("pause")}<span>Pause</span>`
      : `${icon("play")}<span>Resume</span>`;
  }

  async function run(button, request, successMessage) {
    button.disabled = true;
    try {
      Object.assign(product, await request());
      render();
      if (!q(".history").classList.contains("hidden")) loadHistory();
      if (successMessage) say(successMessage(product), "ok");
      return true;
    } catch (error) {
      say(error.message, "err");
      return false;
    } finally {
      button.disabled = false;
    }
  }

  // ---- price history (sparkline + list) ----
  async function loadHistory() {
    const panel = q(".history");
    panel.replaceChildren(el("span", "label", "Loading history…"));
    try {
      const data = await api(API.history(product.id));
      const rows = Array.isArray(data.history) ? data.history : [];
      const head = el("div", "history-head");
      head.append(el("span", "", "Price history"));
      const csv = el("button", "link-btn", "Download CSV");
      csv.type = "button";
      csv.addEventListener("click", () =>
        downloadCsv(API.exportHistory(getEmail(), product.id), `pricehawk_history_${product.id}.csv`));
      head.append(csv);

      if (rows.length === 0) {
        panel.replaceChildren(head, el("span", "label", "No price checks recorded yet."));
        return;
      }
      const list = el("ul", "history-list");
      [...rows].reverse().forEach((row) => {
        const li = el("li", "history-row");
        li.append(el("span", "", shortDate(row.checked_at)), el("strong", "num", money(row.price, currency)));
        list.append(li);
      });
      panel.replaceChildren(head, sparkline(rows.map((r) => Number(r.price)), Number(product.target_price), currency), list);
    } catch (error) {
      panel.replaceChildren(el("span", "label", error.message));
    }
  }

  // ---- actions ----
  // Check now: ask the server; if the store blocks it, read the page through the browser instead.
  let viaBrowser = false;
  async function checkNow() {
    viaBrowser = false;
    try {
      return await api(API.check(product.id), { method: "POST" });
    } catch (error) {
      if (!looksBlocked(error.message)) throw error;
      say(`${store?.name || "The store"} blocked the server. Reading the price through your browser…`, "info");
      const page = await readInBrowser(product.url);
      if (!page) {
        throw new Error(`Couldn't read the price. Open the product page, solve any "robot check", then press Check now again.`);
      }
      viaBrowser = true;
      return api(API.observe, {
        method: "POST",
        body: JSON.stringify({ url: product.url, email: getEmail(), page: pageData(page) })
      });
    }
  }
  q('[data-a="check"]').addEventListener("click", (event) =>
    run(event.currentTarget, checkNow, (p) =>
      (Number(p.current_price) <= Number(p.target_price)
        ? `${money(p.current_price, currency)} — target reached!`
        : `Price is ${money(p.current_price, currency)} (target ${money(p.target_price, currency)}).`) +
      (viaBrowser ? " Read through your browser." : "")));

  q('[data-a="pause"]').addEventListener("click", (event) =>
    run(event.currentTarget,
      () => api(API.product(product.id), { method: "PUT", body: JSON.stringify({ tracking_active: !product.tracking_active }) }),
      (p) => (p.tracking_active ? "Tracking resumed." : "Tracking paused. No checks or emails until you resume.")));

  q('[data-a="history"]').addEventListener("click", (event) => {
    const panel = q(".history");
    const open = panel.classList.toggle("hidden") === false;
    event.currentTarget.setAttribute("aria-expanded", String(open));
    if (open) loadHistory();
  });

  const editInput = q(".target-edit input");
  const setEditing = (on) => {
    q(".target-view").classList.toggle("hidden", on);
    q(".target-edit").classList.toggle("hidden", !on);
    if (on) {
      editInput.value = Number(product.target_price).toFixed(2);
      editInput.focus();
      editInput.select();
    }
  };
  const saveTarget = () => {
    const value = parseFloat(editInput.value);
    if (!Number.isFinite(value) || value <= 0) {
      say("Enter a target price greater than 0.", "err");
      return;
    }
    run(q('[data-a="save"]'),
      () => api(API.product(product.id), { method: "PUT", body: JSON.stringify({ target_price: value }) }),
      (p) => `Target updated to ${money(p.target_price, currency)}.`).then((ok) => ok && setEditing(false));
  };
  q('[data-a="edit"]').addEventListener("click", () => setEditing(true));
  q('[data-a="cancel"]').addEventListener("click", () => setEditing(false));
  q('[data-a="save"]').addEventListener("click", saveTarget);
  editInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") saveTarget();
    if (event.key === "Escape") setEditing(false);
  });

  const demo = q('[data-a="demo"]');
  if (demo) {
    demo.addEventListener("click", (event) => {
      const dropped = Math.max(0.01, Math.round(Number(product.target_price) * 0.95 * 100) / 100);
      run(event.currentTarget,
        () => api(API.simulate(product.id), { method: "POST", body: JSON.stringify({ price: dropped }) }),
        (p) => (p.alert_sent
          ? `Simulated ${money(dropped, currency)}. Alert email sent to ${p.notify_email}.`
          : `Simulated ${money(dropped, currency)}. Email not sent: check SMTP settings in backend/.env.`));
    });
  }

  // Two-step remove instead of a blocking confirm() dialog.
  const remove = q('[data-a="remove"]');
  let armed = null;
  remove.addEventListener("click", async () => {
    if (!armed) {
      remove.dataset.variant = "danger";
      remove.title = "Click again to remove";
      say(`Click the bin again to stop tracking "${product.title || "this product"}".`, "info");
      armed = setTimeout(() => {
        armed = null;
        remove.dataset.variant = "ghost";
        remove.title = "Remove";
      }, 3000);
      return;
    }
    clearTimeout(armed);
    remove.disabled = true;
    try {
      await api(API.product(product.id), { method: "DELETE" });
      item.remove();
      const left = document.querySelectorAll("#items .item").length;
      $("count").textContent = String(left);
      if (left === 0) setEmptyState("Nothing tracked yet", "Track a product and it will show up here.");
      say("Removed from tracking.", "ok");
    } catch (error) {
      remove.disabled = false;
      say(error.message, "err");
    }
  });

  item.refresh = (fresh) => {
    Object.assign(product, fresh);
    render();
  };

  render();
  return item;
}

/** Small SVG line chart of the price history, with the target as a dashed line. */
function sparkline(prices, target, currency) {
  const W = 300, H = 52, PAD = 4;
  const values = prices.length === 1 ? [prices[0], prices[0]] : prices;
  const lo = Math.min(...values, target);
  const hi = Math.max(...values, target);
  const span = hi - lo || 1;
  const x = (i) => PAD + (i / (values.length - 1)) * (W - PAD * 2);
  const y = (v) => H - PAD - ((v - lo) / span) * (H - PAD * 2);
  const points = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");

  const wrap = el("div");
  wrap.innerHTML = `
    <svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Price history chart">
      <polygon class="area" points="${PAD},${H - PAD} ${points} ${W - PAD},${H - PAD}"/>
      <line class="target" x1="0" x2="${W}" y1="${y(target).toFixed(1)}" y2="${y(target).toFixed(1)}"/>
      <polyline class="line" points="${points}" vector-effect="non-scaling-stroke"/>
    </svg>`;
  const legend = el("div", "spark-legend");
  legend.append(el("span", "", `Low ${money(Math.min(...prices), currency)}`),
    el("span", "", `Target ${money(target, currency)}`),
    el("span", "", `High ${money(Math.max(...prices), currency)}`));
  wrap.append(legend);
  return wrap;
}

// =====================================================
// CSV EXPORT
// =====================================================

async function downloadCsv(url, filename) {
  if (!isValidEmail()) {
    say("Enter your alert email first.", "err");
    return;
  }
  try {
    const response = await fetch(url);
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || `Export failed (${response.status})`);
    }
    const href = URL.createObjectURL(await response.blob());
    const link = Object.assign(document.createElement("a"), { href, download: filename });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
    say("CSV downloaded.", "ok");
  } catch (error) {
    say(error.message.includes("fetch") ? "Can't reach the PriceHawk backend." : error.message, "err");
  }
}

$("exportBtn").addEventListener("click", () =>
  downloadCsv(API.exportProducts(getEmail()), "pricehawk_products.csv"));
$("exportHistoryBtn").addEventListener("click", () =>
  downloadCsv(API.exportHistory(getEmail()), "pricehawk_history.csv"));

// Save the email and refresh the count while the user types (debounced).
let emailTimer = null;
$("email").addEventListener("input", () => {
  clearTimeout(emailTimer);
  emailTimer = setTimeout(() => {
    if (!isValidEmail()) return;
    writeStored("pricehawk_email", getEmail());
    refreshCount();
    if (!$("view-list").classList.contains("hidden")) loadList();
  }, 400);
});

// =====================================================
// START
// =====================================================

async function initialize() {
  $("email").value = readStored("pricehawk_email") || "";
  const detection = detect();
  if (await checkBackend()) refreshCount();
  await detection;
}

initialize();
