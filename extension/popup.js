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
    throw new Error((data && data.error) || `Request failed (${response.status})`);
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
// PRODUCT DETECTION (runs inside the shopping page)
// =====================================================

// Injected with chrome.scripting, so it must not use anything from this file.
function readPage() {
  const host = location.hostname.toLowerCase();
  const num = (text) => {
    const n = parseFloat(String(text || "").replace(/,/g, "").replace(/[^0-9.]/g, ""));
    return Number.isFinite(n) && n > 0 ? n : null;
  };
  const text = (selector) => document.querySelector(selector)?.textContent.trim() || null;
  let title = null;
  let price = null;

  // 1. Structured data (most stores publish it)
  try {
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      const json = JSON.parse(script.textContent || "null");
      const items = Array.isArray(json) ? json : (json && json["@graph"]) || [json];
      for (const item of items) {
        const type = item && item["@type"];
        if (type !== "Product" && !(Array.isArray(type) && type.includes("Product"))) continue;
        title = title || (item.name ? String(item.name).trim() : null);
        const offers = item.offers;
        const offer = Array.isArray(offers) ? offers[0] : offers?.offers ? offers.offers[0] : offers;
        price = price || num(offer?.price ?? offer?.lowPrice);
      }
    }
  } catch { /* broken JSON-LD: fall back to the page */ }

  // 2. Store-specific selectors
  if (host === "books.toscrape.com") {
    title = title || text(".product_main h1");
    price = price || num(text(".product_main .price_color"));
  } else if (host.includes("amazon.")) {
    title = title || text("#productTitle") || text("#title");
    price = price || num(text(
      "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen, #corePrice_desktop .a-price .a-offscreen," +
      "#apex_desktop .a-price .a-offscreen, .priceToPay .a-offscreen, #priceblock_dealprice, #priceblock_ourprice"
    ));
  } else if (host.includes("flipkart.com")) {
    title = title || text("span.B_NuCI") || text("span.VU-ZEz") || text("h1.yhB1nd span") || text("h1");
    price = price || num(text("div.Nx9bqj.CxhGGd, div._30jeq3._16Jk6d, div.Nx9bqj, div._30jeq3"));
  } else if (host.includes("ebay.")) {
    title = title || text("h1.x-item-title__mainTitle span") || text("h1#itemTitle");
    price = price || num(text("div.x-price-primary span.ux-textspans, span#prcIsum, span#mm-saleDscPrc"));
  } else if (host.includes("myntra.com")) {
    const name = [text("h1.pdp-title"), text("h1.pdp-name")].filter(Boolean).join(" ");
    title = title || name || null;
    price = price || num(text("span.pdp-price strong, span.pdp-price"));
  }
  return { title, price, url: location.href };
}

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
  $("pPrice").textContent = money(product.price, product.currency);
  $("pUrl").textContent = product.url;
  $("pUrl").href = product.url;
  $("pUrl").classList.remove("hidden");
  $("targetCurrencyAddon").textContent = product.currency;
  $("target").placeholder = suggestedTarget(10)?.toFixed(2) || "0.00";
  updateGauge();
}

function showNoProduct(title, hint, statusLabel, tone) {
  detected = null;
  $("productCard").dataset.state = "empty";
  $("pStore").classList.add("hidden");
  $("pTitle").textContent = title;
  $("pHint").textContent = hint;
  $("pHint").classList.toggle("hidden", !hint);
  $("pUrl").classList.add("hidden");
  $("target").placeholder = "0.00";
  setDetectStatus(statusLabel, tone);
  updateGauge();
}

async function detect() {
  $("productCard").dataset.state = "loading";
  setDetectStatus("Looking…", "loading");

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

  // 1. Read the page the user is looking at (instant, no extra request)
  let product = null;
  try {
    const [result] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: readPage });
    product = result?.result;
  } catch (error) {
    console.warn("PriceHawk: page read failed, asking the backend instead", error);
  }

  // 2. Fall back to the backend scraper
  if (!product?.title || !Number.isFinite(product?.price)) {
    try {
      const data = await api(API.preview, { method: "POST", body: JSON.stringify({ url: tab.url }) });
      product = { title: data.title, price: data.price, url: data.url, currency: data.currency };
    } catch (error) {
      showNoProduct("Couldn't read this product", error.message, "Not found", "amber");
      return;
    }
  }

  showProduct({ ...product, store: store.name, currency: product.currency || store.currency });
  setDetectStatus("Detected", "green");
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
    const store = storeInfo(data.url) || storeInfo(url);
    showProduct({ title: data.title, price: data.price, url: data.url,
      currency: data.currency || store?.currency, store: store?.name });
    setDetectStatus(data.already_tracked ? "Already tracked" : "Verified", data.already_tracked ? "amber" : "green");
    say(data.already_tracked ? "You're already tracking this product." : "Product found. Set a target and start tracking.", "ok");
  } catch (error) {
    setDetectStatus("Not found", "amber");
    say(error.message, "err");
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

  try {
    if (manual && $("manualUrl").value.trim()) {
      url = validateProductUrl($("manualUrl").value.trim());
    } else if (detected?.url) {
      url = detected.url;
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
      body: JSON.stringify({ url, target_price: target, email })
    });
    const currency = product.currency || detected?.currency;
    setDetectStatus("Tracking", "green");
    say(product.alert_sent
      ? `Already below your target! Alert sent to ${email}.`
      : `Tracking started. We'll email ${email} when it drops to ${money(target, currency)}.`, "ok");
    refreshCount();
  } catch (error) {
    if (/already tracking/i.test(error.message)) {
      setDetectStatus("Already tracked", "amber");
      say("You're already tracking this product. Change its target in the Tracked tab.", "info");
    } else {
      say(error.message, "err");
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
  } catch (error) {
    if (requestId !== listRequestId) return;
    setEmptyState("Couldn't load your products", error.message);
  }
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
  if (p.last_error) return { key: "error", label: "Check failed", tone: "red" };
  if (hit) return { key: "hit", label: p.alert_sent ? "Alert sent" : "Target reached", tone: "green" };
  return { key: "watching", label: "Watching", tone: "amber" };
}

function createCard(product) {
  const store = storeInfo(product.url);
  const currency = product.currency || store?.currency || "";
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
    gap.textContent = now <= target
      ? `${money(target - now, currency)} below target`
      : `${money(now - target, currency)} to go`;
    q(".checked").textContent = timeAgo(product.last_checked_at);

    q(".item-error").textContent = product.last_error ? `Last check failed: ${product.last_error}` : "";
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
  q('[data-a="check"]').addEventListener("click", (event) =>
    run(event.currentTarget, () => api(API.check(product.id), { method: "POST" }), (p) =>
      Number(p.current_price) <= Number(p.target_price)
        ? `${money(p.current_price, currency)} — target reached!`
        : `Price is ${money(p.current_price, currency)} (target ${money(p.target_price, currency)}).`));

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
