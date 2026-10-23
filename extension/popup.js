"use strict";

console.log("PriceHawk popup.js loaded");

// =====================================================
// CONFIGURATION AND ENDPOINTS
// =====================================================

const API_BASE = "http://127.0.0.1:5000";
const SUPPORTED_RETAILERS = [
  "Books to Scrape",
  "Amazon",
  "Flipkart",
  "eBay",
  "Myntra"
];

function isSupportedUrl(urlStr) {
  try {
    const parsed = new URL(urlStr);
    const host = parsed.hostname.toLowerCase();
    return (
      host === "books.toscrape.com" ||
      /(^|\.)amazon\.(com|in|co\.uk|ca|de|fr|es|it|com\.au|co\.jp|nl|com\.br|com\.mx|ae|sa|sg)$/i.test(host) ||
      /(^|\.)flipkart\.com$/i.test(host) ||
      /(^|\.)ebay\.(com|co\.uk|ca|com\.au|de|fr|es|it|nl|ie|at|ch|be|pl)$/i.test(host) ||
      /(^|\.)myntra\.com$/i.test(host)
    );
  } catch {
    return false;
  }
}

function getCurrencySymbol(urlStr, fallback = "£") {
  try {
    const parsed = new URL(urlStr);
    const host = parsed.hostname.toLowerCase();
    if (/(^|\.)amazon\./i.test(host)) {
      if (host.endsWith(".in")) return "₹";
      if (host.endsWith(".co.uk")) return "£";
      if (/\.(de|fr|es|it|nl)$/i.test(host)) return "€";
      if (host.endsWith(".ca")) return "CA$";
      if (host.endsWith(".com.au")) return "AU$";
      if (host.endsWith(".co.jp")) return "¥";
      return "$";
    }
    if (/(^|\.)flipkart\.com$/i.test(host)) return "₹";
    if (/(^|\.)myntra\.com$/i.test(host)) return "₹";
    if (/(^|\.)ebay\./i.test(host)) {
      if (host.endsWith(".co.uk")) return "£";
      if (/\.(de|fr|es|it|nl|ie|at)$/i.test(host)) return "€";
      if (host.endsWith(".ca")) return "CA$";
      if (host.endsWith(".com.au")) return "AU$";
      return "$";
    }
    if (host === "books.toscrape.com") return "£";
  } catch {}
  return fallback;
}

const API = {
  health: `${API_BASE}/api/health`,
  preview: `${API_BASE}/api/preview`,
  list: (email) => `${API_BASE}/api/products?email=${encodeURIComponent(email)}`,
  add: `${API_BASE}/api/products`,
  get: (id) => `${API_BASE}/api/products/${encodeURIComponent(id)}`,
  update: (id) => `${API_BASE}/api/products/${encodeURIComponent(id)}`,
  remove: (id) => `${API_BASE}/api/products/${encodeURIComponent(id)}`,
  check: (id) => `${API_BASE}/api/products/${encodeURIComponent(id)}/check`,
  history: (id) => `${API_BASE}/api/products/${encodeURIComponent(id)}/history`,
  simulate: (id) => `${API_BASE}/api/products/${encodeURIComponent(id)}/simulate`,
  export: (email) => `${API_BASE}/api/export/products.csv?email=${encodeURIComponent(email)}`,
  exportHistory: (email, id) =>
    `${API_BASE}/api/export/history.csv?email=${encodeURIComponent(email)}${
      id ? `&product_id=${encodeURIComponent(id)}` : ""
    }`
};

// =====================================================
// STATE AND HELPERS
// =====================================================

const $ = (id) => document.getElementById(id);

let detected = null; // { title, price, url, currency }
let demoMode = false;
let currentListRequestId = 0;
let isSubmittingTrack = false;

function say(message, kind = "") {
  const alertBox = $("alert");
  if (!alertBox) return;

  alertBox.classList.toggle("hidden", !message);
  alertBox.dataset.variant = kind === "err" ? "destructive" : "default";
  $("alertText").textContent = message || "";
}

function money(value, currency = null, contextUrl = null) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const sym = currency || (contextUrl ? getCurrencySymbol(contextUrl) : (detected?.currency || "£"));
  return `${sym}${number.toFixed(2)}`;
}

function formatDate(isoString) {
  if (!isoString) return "—";
  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return String(isoString);
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch {
    return String(isoString);
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function getEmail() {
  const input = $("email");
  return input ? input.value.trim() : "";
}

const EMAIL_PATTERN = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/;

function isValidEmail(email) {
  const value = (email !== undefined ? email : getEmail()).trim();
  return Boolean(value && value.length <= 254 && EMAIL_PATTERN.test(value));
}

function saveEmail(email) {
  try {
    if (email) {
      localStorage.setItem("pricehawk_email", email.trim());
    }
  } catch (e) {
    console.warn("Could not save email to localStorage:", e);
  }
}

function loadSavedEmail() {
  try {
    const saved = localStorage.getItem("pricehawk_email");
    if (saved && $("email")) {
      $("email").value = saved;
    }
  } catch (e) {
    console.warn("Could not read email from localStorage:", e);
  }
}

function setDetectionStatus(message, state = "loading") {
  const textEl = $("detectText");
  const statusEl = $("detectStatus");
  if (textEl) textEl.textContent = message;
  if (statusEl) statusEl.dataset.state = state;
}

function setTrackingLoading(loading) {
  const btn = $("trackBtn");
  const spin = $("trackSpin");
  const text = $("trackBtnText");

  if (btn) btn.disabled = loading;
  if (spin) spin.classList.toggle("hidden", !loading);
  if (text) text.textContent = loading ? "Please wait..." : "Start Tracking";
}

// =====================================================
// BACKEND REQUEST HELPER
// =====================================================

async function api(url, options = {}) {
  let response;

  try {
    response = await fetch(url, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers
      }
    });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("Cannot reach the PriceHawk backend. Start Flask on port 5000.");
    }
    throw error;
  }

  const contentType = response.headers.get("content-type") || "";
  let data;

  if (contentType.includes("application/json")) {
    data = await response.json().catch(() => ({}));
  } else {
    data = await response.text().catch(() => "");
  }

  if (!response.ok) {
    const message =
      typeof data === "object" && data !== null
        ? data.error || data.message
        : null;

    throw new Error(message || `Request failed with status ${response.status}.`);
  }

  return data;
}

// =====================================================
// BACKEND CONNECTION HEALTH CHECK
// =====================================================

async function testBackendConnection() {
  try {
    const data = await api(API.health);
    console.log("PriceHawk backend connected:", data);
    demoMode = Boolean(data.demo_mode);
    return true;
  } catch (error) {
    console.error("PriceHawk backend connection failed:", error);
    say(error.message, "err");
    return false;
  }
}

// =====================================================
// NAVIGATION TABS
// =====================================================

function show(view) {
  document.querySelectorAll(".tabs-trigger").forEach((button) => {
    const active = button.dataset.view === view;
    button.dataset.state = active ? "active" : "inactive";
    button.setAttribute("aria-selected", String(active));
  });

  $("view-track").classList.toggle("hidden", view !== "track");
  $("view-list").classList.toggle("hidden", view !== "list");

  if (view === "list") {
    loadList();
  }
}

document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => {
    show(button.dataset.view);
  });
});

// =====================================================
// PRODUCT DETECTION VIA ACTIVE TAB DOM
// =====================================================

function readPage() {
  const url = location.href;
  const host = location.hostname.toLowerCase();
  let title = null;
  let price = null;
  let currency = null;

  // 1. Try Schema.org JSON-LD first
  try {
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    for (const script of scripts) {
      const text = script.textContent;
      if (!text) continue;
      const json = JSON.parse(text);
      const items = Array.isArray(json) ? json : (json["@graph"] || [json]);
      for (const item of items) {
        if (item && (item["@type"] === "Product" || (Array.isArray(item["@type"]) && item["@type"].includes("Product")))) {
          if (item.name) title = item.name.trim();
          const offers = item.offers;
          const offer = Array.isArray(offers) ? offers[0] : (offers?.offers ? offers.offers[0] : offers);
          if (offer) {
            const rawPrice = offer.price || offer.lowPrice;
            if (rawPrice !== undefined && rawPrice !== null) {
              const num = parseFloat(String(rawPrice).replace(/,/g, "").replace(/[^0-9.]/g, ""));
              if (Number.isFinite(num) && num > 0) price = num;
            }
            if (offer.priceCurrency) {
              const curMap = { USD: "$", GBP: "£", INR: "₹", EUR: "€", CAD: "CA$", AUD: "AU$" };
              currency = curMap[offer.priceCurrency] || offer.priceCurrency;
            }
          }
        }
      }
    }
  } catch (e) {}

  // 2. Retailer specific DOM fallback
  if (host.includes("books.toscrape.com")) {
    title = title || document.querySelector(".product_main h1")?.textContent.trim();
    const pText = document.querySelector(".product_main .price_color")?.textContent.trim();
    if (pText && price === null) {
      const num = parseFloat(pText.replace(/[^0-9.]/g, ""));
      if (Number.isFinite(num)) price = num;
    }
    currency = "£";
  } else if (host.includes("amazon.")) {
    title = title || (
      document.querySelector("#productTitle")?.textContent.trim() ||
      document.querySelector("#title")?.textContent.trim()
    );
    const pEl = document.querySelector(
      "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen, " +
      "#corePrice_desktop .a-price .a-offscreen, " +
      "#apex_desktop .a-price .a-offscreen, " +
      ".priceToPay .a-offscreen, " +
      "#priceblock_dealprice, " +
      "#priceblock_ourprice, " +
      ".a-price .a-offscreen"
    );
    if (pEl && price === null) {
      const num = parseFloat(pEl.textContent.replace(/,/g, "").replace(/[^0-9.]/g, ""));
      if (Number.isFinite(num)) price = num;
    }
    if (!currency) {
      currency = host.endsWith(".in") ? "₹" : (host.endsWith(".co.uk") ? "£" : "$");
    }
  } else if (host.includes("flipkart.com")) {
    title = title || (
      document.querySelector("span.B_NuCI")?.textContent.trim() ||
      document.querySelector("h1._6EBuvT span.VU-ZEz")?.textContent.trim() ||
      document.querySelector("span.VU-ZEz")?.textContent.trim() ||
      document.querySelector("h1.yhB1nd span")?.textContent.trim()
    );
    const pEl = document.querySelector("div._30jeq3._16Jk6d, div.Nx9bqj.CxhGGd, div._30jeq3, div.Nx9bqj");
    if (pEl && price === null) {
      const num = parseFloat(pEl.textContent.replace(/,/g, "").replace(/[^0-9.]/g, ""));
      if (Number.isFinite(num)) price = num;
    }
    currency = "₹";
  } else if (host.includes("ebay.")) {
    title = title || (
      document.querySelector("h1.x-item-title__mainTitle span")?.textContent.trim() ||
      document.querySelector("h1#itemTitle")?.textContent.trim()
    );
    const pEl = document.querySelector("div.x-price-primary span.ux-textspans, span#prcIsum, span#mm-saleDscPrc");
    if (pEl && price === null) {
      const num = parseFloat(pEl.textContent.replace(/,/g, "").replace(/[^0-9.]/g, ""));
      if (Number.isFinite(num)) price = num;
    }
    if (!currency) {
      currency = host.endsWith(".co.uk") ? "£" : "$";
    }
  } else if (host.includes("myntra.com")) {
    const brand = document.querySelector("h1.pdp-title")?.textContent.trim() || "";
    const name = document.querySelector("h1.pdp-name")?.textContent.trim() || "";
    title = title || (brand ? `${brand} ${name}`.trim() : name);
    const pEl = document.querySelector("span.pdp-price strong, span.pdp-price");
    if (pEl && price === null) {
      const num = parseFloat(pEl.textContent.replace(/,/g, "").replace(/[^0-9.]/g, ""));
      if (Number.isFinite(num)) price = num;
    }
    currency = "₹";
  }

  return {
    title: title || null,
    price: Number.isFinite(price) ? price : null,
    currency: currency || null,
    url
  };
}

async function detect() {
  console.log("PriceHawk detection started");
  setDetectionStatus("Looking...", "loading");

  try {
    if (!chrome?.tabs?.query) {
      throw new Error("Chrome extension tabs API is unavailable.");
    }

    const [tab] = await chrome.tabs.query({
      active: true,
      currentWindow: true
    });

    if (!tab?.id || !tab.url) {
      throw new Error("Cannot identify the active browser tab.");
    }

    if (!isSupportedUrl(tab.url)) {
      throw new Error("Open a product page on Amazon, Flipkart, eBay, Myntra, or Books to Scrape.");
    }

    let product = null;

    // First attempt: read the active DOM directly
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: readPage
      });
      product = results?.[0]?.result;
    } catch (scriptErr) {
      console.warn("Direct DOM script injection failed; falling back to backend preview:", scriptErr);
    }

    // Fallback attempt: if DOM extraction didn't find price, query backend preview
    if (!product || !product.title || product.price === null || !Number.isFinite(product.price)) {
      try {
        const previewData = await api(API.preview, {
          method: "POST",
          body: JSON.stringify({
            url: tab.url,
            email: isValidEmail() ? getEmail() : undefined
          })
        });
        if (previewData && previewData.title && Number.isFinite(previewData.price)) {
          product = {
            title: previewData.title,
            price: previewData.price,
            currency: previewData.currency || getCurrencySymbol(previewData.url),
            url: previewData.url
          };
        }
      } catch (previewErr) {
        console.warn("Backend preview fallback failed:", previewErr);
      }
    }

    if (!product || !product.title || product.price === null || !Number.isFinite(product.price)) {
      throw new Error("Could not read the product title or price.");
    }

    const sym = product.currency || getCurrencySymbol(product.url);
    product.currency = sym;
    detected = product;

    $("pTitle").textContent = product.title;
    $("pPrice").textContent = money(product.price, sym);
    $("pUrl").textContent = product.url;

    if ($("targetCurrencyAddon")) {
      $("targetCurrencyAddon").textContent = sym;
    }

    setDetectionStatus("Product detected", "ok");
    say("");
    console.log("PriceHawk detection successful:", product);
  } catch (error) {
    detected = null;

    $("pTitle").textContent = "No product detected";
    $("pPrice").textContent = "—";
    $("pUrl").textContent = "";

    setDetectionStatus("Detection failed", "warn");
    console.warn("PriceHawk detection:", error.message);
    say(error.message, "err");
  } finally {
    updateGauge();
  }
}

// =====================================================
// TARGET PRICE GAUGE
// =====================================================

function updateGauge() {
  const target = parseFloat($("target").value);
  const price = detected?.price;
  const fill = $("gaugeFill");

  if (!Number.isFinite(target) || target <= 0 || !Number.isFinite(price) || price <= 0) {
    fill.style.width = "0%";
    fill.classList.remove("hit");
    $("gaugeText").textContent = "Set a target";
    return;
  }

  const percentage = Math.min(100, (target / price) * 100);
  fill.style.width = `${percentage}%`;

  const reached = price <= target;
  fill.classList.toggle("hit", reached);

  $("gaugeText").textContent = reached
    ? "Target reached!"
    : `${money(price - target)} to go`;
}

$("target").addEventListener("input", updateGauge);

// =====================================================
// MANUAL PRODUCT URL TOGGLE & PREVIEW
// =====================================================

$("manualToggle").addEventListener("click", () => {
  const manualField = $("manualField");
  const willShow = manualField.classList.contains("hidden");

  manualField.classList.toggle("hidden");
  $("manualToggle").textContent = willShow
    ? "Use the detected product"
    : "Enter a product link instead";

  $("manualToggle").setAttribute("aria-expanded", String(willShow));

  if (!willShow) {
    $("manualUrl").value = "";
    if (detected) {
      $("pTitle").textContent = detected.title || "No product detected";
      $("pPrice").textContent = money(detected.price);
      $("pUrl").textContent = detected.url || "";
      setDetectionStatus("Product detected", "ok");
    } else {
      detect();
    }
  }

  say("");
});

// Manual preview button handler
$("previewBtn").addEventListener("click", async () => {
  const rawUrl = $("manualUrl").value.trim();
  if (!rawUrl) {
    say("Enter a product link to preview.", "err");
    return;
  }

  try {
    const validUrl = validateProductUrl(rawUrl);
    say("Checking link preview...");
    $("previewBtn").disabled = true;

    const data = await api(API.preview, {
      method: "POST",
      body: JSON.stringify({
        url: validUrl,
        email: isValidEmail() ? getEmail() : undefined
      })
    });

    const sym = data.currency || getCurrencySymbol(data.url);
    detected = {
      title: data.title,
      price: data.price,
      currency: sym,
      url: data.url
    };

    $("pTitle").textContent = data.title;
    $("pPrice").textContent = money(data.price, sym);
    $("pUrl").textContent = data.url;
    if ($("targetCurrencyAddon")) {
      $("targetCurrencyAddon").textContent = sym;
    }

    setDetectionStatus("Product verified", "ok");
    updateGauge();

    if (data.already_tracked) {
      say("You are already tracking this product.", "ok");
    } else {
      say("Product verified! Enter your target price and start tracking.", "ok");
    }
  } catch (error) {
    console.error("Preview error:", error);
    say(error.message, "err");
    setDetectionStatus("Preview failed", "warn");
  } finally {
    $("previewBtn").disabled = false;
  }
});

// =====================================================
// PRODUCT URL VALIDATION
// =====================================================

function validateProductUrl(value) {
  let parsed;

  try {
    parsed = new URL(value);
  } catch {
    throw new Error("Enter a valid product URL.");
  }

  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("Only HTTP and HTTPS URLs are supported.");
  }

  const host = parsed.hostname.toLowerCase();
  const path = parsed.pathname;

  // 1. Books to Scrape
  if (host === "books.toscrape.com") {
    if (!path.includes("/catalogue/") && !path.endsWith(".html")) {
      throw new Error("Open a valid Books to Scrape product page.");
    }
    return parsed.href;
  }

  // 2. Amazon
  if (/(^|\.)amazon\.(com|in|co\.uk|ca|de|fr|es|it|com\.au|co\.jp|nl|com\.br|com\.mx|ae|sa|sg)$/i.test(host)) {
    const hasAsin = /(?:\/dp\/|\/gp\/product\/|\/gp\/aw\/d\/|\/d\/)([A-Za-z0-9]{10})/i.test(path) ||
                    /[?&]asin=([A-Za-z0-9]{10})/i.test(parsed.search);
    if (!hasAsin) {
      throw new Error("Enter a valid Amazon product URL with a 10-character ASIN.");
    }
    return parsed.href;
  }

  // 3. Flipkart
  if (/(^|\.)flipkart\.com$/i.test(host)) {
    const hasProduct = path.includes("/p/") || /[?&]pid=/i.test(parsed.search);
    if (!hasProduct) {
      throw new Error("Enter a valid Flipkart product URL.");
    }
    return parsed.href;
  }

  // 4. eBay
  if (/(^|\.)ebay\.(com|co\.uk|ca|com\.au|de|fr|es|it|nl|ie|at|ch|be|pl)$/i.test(host)) {
    const hasItemId = /\/itm\/(?:[^\/]+\/)?(\d{9,14})/i.test(path) || /[?&]item=(\d{9,14})/i.test(parsed.search);
    if (!hasItemId) {
      throw new Error("Enter a valid eBay item URL with a numeric item ID.");
    }
    return parsed.href;
  }

  // 5. Myntra
  if (/(^|\.)myntra\.com$/i.test(host)) {
    const hasStyleId = /\/(\d{5,10})(?:\/buy|\/?$)/i.test(path);
    if (!hasStyleId) {
      throw new Error("Enter a valid Myntra product URL with a style ID.");
    }
    return parsed.href;
  }

  throw new Error("Supported stores: Amazon, Flipkart, eBay, Myntra, and Books to Scrape.");
}

// =====================================================
// ADD PRODUCT TO TRACKING
// =====================================================

$("trackBtn").addEventListener("click", async () => {
  if (isSubmittingTrack) {
    return; // Prevent duplicate concurrent submissions
  }

  const target = parseFloat($("target").value);
  const email = getEmail();
  const manual = !$("manualField").classList.contains("hidden");

  let url;

  try {
    if (manual) {
      url = validateProductUrl($("manualUrl").value.trim());
    } else {
      if (!detected?.url) {
        throw new Error("No product detected. Open a supported product page or enter a link.");
      }
      url = validateProductUrl(detected.url);
    }

    if (!Number.isFinite(target) || target <= 0) {
      throw new Error("Enter a target price greater than zero.");
    }

    if (!isValidEmail(email)) {
      throw new Error("Enter a valid notification email address.");
    }
  } catch (error) {
    say(error.message, "err");
    return;
  }

  isSubmittingTrack = true;
  setTrackingLoading(true);
  say("Starting product tracking...");

  try {
    saveEmail(email);

    const result = await api(API.add, {
      method: "POST",
      body: JSON.stringify({
        url,
        target_price: target,
        email
      })
    });

    console.log("PriceHawk product created:", result);
    say("Product tracking started successfully!", "ok");

    // Invalidate stale list requests and update tracked list and count
    loadList().catch((err) => console.error("List refresh error:", err));
    refreshCount().catch((err) => console.error("Count refresh error:", err));
  } catch (error) {
    const message = String(error.message || "");
    const lowerMessage = message.toLowerCase();

    if (
      lowerMessage.includes("already tracking") ||
      lowerMessage.includes("already tracks this product") ||
      lowerMessage.includes("duplicate")
    ) {
      say("You're already tracking this product!", "ok");
    } else {
      console.error("PriceHawk tracking error:", error);
      say(message || "Unable to start tracking.", "err");
    }
  } finally {
    isSubmittingTrack = false;
    setTrackingLoading(false);
  }
});

// =====================================================
// LOAD TRACKED PRODUCTS LIST
// =====================================================

async function loadList() {
  const requestId = ++currentListRequestId;
  const list = $("items");
  const empty = $("empty");
  const email = getEmail();

  if (!isValidEmail(email)) {
    $("count").textContent = "0";
    list.replaceChildren();
    empty.classList.remove("hidden");
    empty.querySelector(".empty-title").textContent = "Email required";
    empty.querySelector(".empty-desc").textContent =
      "Enter your notification email on the Track tab.";
    return;
  }

  try {
    const data = await api(API.list(email));

    // Stale asynchronous response check: discard if newer request in flight
    if (requestId !== currentListRequestId) {
      return;
    }

    const products = Array.isArray(data.products) ? data.products : [];

    $("count").textContent = String(products.length);
    list.replaceChildren();

    empty.querySelector(".empty-title").textContent = "Nothing tracked yet";
    empty.querySelector(".empty-desc").textContent =
      "Track a product and it will show up here.";
    empty.classList.toggle("hidden", products.length > 0);

    products.forEach((product) => {
      list.appendChild(card(product));
    });

    console.log("PriceHawk tracked products loaded:", products.length);
  } catch (error) {
    if (requestId !== currentListRequestId) {
      return;
    }

    console.error("PriceHawk list error:", error);
    list.replaceChildren();
    empty.classList.remove("hidden");
    empty.querySelector(".empty-title").textContent = "Cannot load tracked products";
    empty.querySelector(".empty-desc").textContent = error.message;
  }
}

// Refresh list button listener
$("refreshListBtn").addEventListener("click", async () => {
  const btn = $("refreshListBtn");
  btn.disabled = true;
  btn.textContent = "Refreshing...";
  try {
    await loadList();
    await refreshCount();
    say("Tracked products refreshed.", "ok");
  } catch (error) {
    say(error.message, "err");
  } finally {
    btn.disabled = false;
    btn.textContent = "Refresh";
  }
});

// =====================================================
// TRACKED PRODUCT CARD WITH FULL CONTROLS
// =====================================================

function card(product) {
  const currentPrice = Number(
    product.current_price !== undefined ? product.current_price : product.price
  );
  const targetPrice = Number(product.target_price);
  const sym = getCurrencySymbol(product.url);

  const hit =
    Number.isFinite(currentPrice) &&
    Number.isFinite(targetPrice) &&
    currentPrice <= targetPrice;

  const item = document.createElement("li");
  item.className = "card item";
  item.dataset.id = String(product.id);
  item.dataset.url = product.url;

  if (hit) {
    item.dataset.hit = "";
  }

  item.innerHTML = `
    <div class="card-header">
      <div>
        <div class="card-title"></div>
        <a href="${escapeHtml(product.url)}" target="_blank" rel="noopener noreferrer" class="product-link truncate" style="max-width: 200px; display: block;" title="Open product page">
          ${escapeHtml(product.url)}
        </a>
      </div>

      <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
        <span class="badge status-badge" data-variant="${hit ? "warn" : "outline"}">
          ${hit ? "Target reached" : "Watching"}
        </span>
        ${
          !product.tracking_active
            ? `<span class="badge paused-badge" data-variant="outline" style="font-size: 11px;">Paused</span>`
            : ""
        }
      </div>
    </div>

    <div class="row">
      <div>
        <span class="muted">Current</span>
        <strong class="now">${money(currentPrice, sym)}</strong>
      </div>

      <div>
        <span class="muted">Target</span>
        <div style="display: flex; align-items: center; gap: 6px;">
          <strong class="target-val">${money(targetPrice, sym)}</strong>
          <button class="btn btn-inline-edit" data-a="edit-target" type="button" title="Change target price">
            Edit
          </button>
        </div>
      </div>
    </div>

    <!-- Inline Target Price Edit Form -->
    <div class="edit-target-form hidden">
      <div class="input-group" style="height: 30px; flex: 1;">
        <span class="input-addon" style="padding-left: 8px;">${sym}</span>
        <input class="edit-target-input" type="number" step="0.01" min="0.01" value="${targetPrice.toFixed(2)}" style="padding: 0 8px; font-size: 13px;">
      </div>
      <button class="btn" data-size="sm" data-a="save-target" type="button" style="height: 30px; padding: 0 10px; font-size: 12px;">Save</button>
      <button class="btn" data-variant="ghost" data-size="sm" data-a="cancel-target" type="button" style="height: 30px; padding: 0 8px; font-size: 12px;">Cancel</button>
    </div>

    <div class="card-footer">
      <button class="btn" data-variant="outline" data-size="sm" data-a="check" type="button">
        Check now
      </button>

      <button class="btn" data-variant="outline" data-size="sm" data-a="toggle-pause" type="button">
        ${product.tracking_active ? "Pause" : "Resume"}
      </button>

      <button class="btn" data-variant="outline" data-size="sm" data-a="history" type="button">
        History
      </button>

      ${
        demoMode
          ? `<button class="btn" data-variant="outline" data-size="sm" data-a="simulate" style="color: var(--warn); border-color: rgba(255,184,0,0.4);" type="button" title="Demo mode: fake price drop to test email alert">Demo drop</button>`
          : ""
      }

      <button class="btn" data-variant="ghost" data-size="sm" data-destructive data-a="del" type="button">
        Remove
      </button>
    </div>

    <!-- Expandable Price History Panel -->
    <div class="history-panel hidden">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        <span style="font-weight: 600; font-size: 12px;">Price History</span>
        <button class="btn" data-variant="link" data-a="export-item-history" type="button" style="font-size: 11px;">
          Download CSV
        </button>
      </div>
      <div class="history-content">
        <span class="muted">Loading history...</span>
      </div>
    </div>
  `;

  item.querySelector(".card-title").textContent = product.title || "Untitled product";

  const checkButton = item.querySelector('[data-a="check"]');
  const togglePauseButton = item.querySelector('[data-a="toggle-pause"]');
  const historyButton = item.querySelector('[data-a="history"]');
  const removeButton = item.querySelector('[data-a="del"]');
  const editTargetButton = item.querySelector('[data-a="edit-target"]');
  const saveTargetButton = item.querySelector('[data-a="save-target"]');
  const cancelTargetButton = item.querySelector('[data-a="cancel-target"]');
  const editForm = item.querySelector(".edit-target-form");
  const editInput = item.querySelector(".edit-target-input");
  const historyPanel = item.querySelector(".history-panel");
  const historyContent = item.querySelector(".history-content");
  const exportHistoryItemBtn = item.querySelector('[data-a="export-item-history"]');
  const simulateButton = item.querySelector('[data-a="simulate"]');

  // Load this card's price history into its history panel
  async function loadCardHistory() {
    historyContent.innerHTML = `<span class="muted">Loading history...</span>`;

    try {
      const data = await api(API.history(product.id));
      const history = Array.isArray(data.history) ? data.history : [];

      if (history.length === 0) {
        historyContent.innerHTML = `<span class="muted">No price observations recorded yet.</span>`;
        return;
      }

      const ul = document.createElement("ul");
      ul.className = "history-list";

      history.forEach((h) => {
        const li = document.createElement("li");
        li.className = "history-row";
        li.innerHTML = `
          <span class="muted">${formatDate(h.checked_at)}</span>
          <strong>${money(h.price, sym)}</strong>
        `;
        ul.appendChild(li);
      });

      historyContent.replaceChildren(ul);
    } catch (error) {
      console.error("Fetch history failed:", error);
      historyContent.innerHTML = `<span class="muted" style="color: var(--destructive);">${escapeHtml(
        error.message
      )}</span>`;
    }
  }

  // 1. Manual Price Check
  checkButton.addEventListener("click", async () => {
    checkButton.disabled = true;
    checkButton.textContent = "Checking...";
    say("");

    try {
      const result = await api(API.check(product.id), { method: "POST" });
      console.log("Price check result:", result);

      const freshPrice = Number(result.current_price);
      const latestTarget = Number(
        result.target_price !== undefined ? result.target_price : product.target_price
      );

      // Update in-memory product state
      product.current_price = freshPrice;
      product.target_price = latestTarget;
      product.alert_sent = Boolean(result.alert_sent);
      product.last_checked_at = result.last_checked_at;
      if (result.title) product.title = result.title;

      // Update DOM immediately in-place
      item.querySelector(".now").textContent = money(freshPrice, sym);
      item.querySelector(".target-val").textContent = money(latestTarget, sym);
      item.querySelector(".card-title").textContent = product.title;

      const hit =
        Number.isFinite(freshPrice) &&
        Number.isFinite(latestTarget) &&
        freshPrice <= latestTarget;

      if (hit) {
        item.dataset.hit = "";
      } else {
        delete item.dataset.hit;
      }

      const statusBadge = item.querySelector(".status-badge");
      statusBadge.dataset.variant = hit ? "warn" : "outline";
      statusBadge.textContent = hit ? "Target reached" : "Watching";

      // If history panel is open, refresh its history in-place
      if (!historyPanel.classList.contains("hidden")) {
        loadCardHistory();
      }

      if (hit) {
        say(`Checked: ${money(freshPrice, sym)} — Target reached!`, "ok");
      } else {
        say(`Checked: ${money(freshPrice, sym)} (Target: ${money(latestTarget, sym)})`, "ok");
      }

      refreshCount().catch(() => {});
    } catch (error) {
      console.error("Price check failed:", error);
      say(error.message || "Failed to check price. Please try again.", "err");
    } finally {
      checkButton.disabled = false;
      checkButton.textContent = "Check now";
    }
  });

  // 2. Pause / Resume Tracking
  togglePauseButton.addEventListener("click", async () => {
    togglePauseButton.disabled = true;
    const newActiveState = !product.tracking_active;

    try {
      const updated = await api(API.update(product.id), {
        method: "PUT",
        body: JSON.stringify({ tracking_active: newActiveState })
      });

      product.tracking_active = updated.tracking_active;
      togglePauseButton.textContent = product.tracking_active ? "Pause" : "Resume";

      let pausedBadge = item.querySelector(".paused-badge");
      if (!product.tracking_active) {
        if (!pausedBadge) {
          pausedBadge = document.createElement("span");
          pausedBadge.className = "badge paused-badge";
          pausedBadge.dataset.variant = "outline";
          pausedBadge.style.fontSize = "11px";
          pausedBadge.textContent = "Paused";
          item.querySelector(".card-header > div:last-child").appendChild(pausedBadge);
        }
      } else if (pausedBadge) {
        pausedBadge.remove();
      }

      say(`Tracking ${product.tracking_active ? "resumed" : "paused"}.`, "ok");
    } catch (error) {
      console.error("Toggle tracking failed:", error);
      say(error.message, "err");
    } finally {
      togglePauseButton.disabled = false;
    }
  });

  // 3. Edit Target Price Inline
  editTargetButton.addEventListener("click", () => {
    editForm.classList.toggle("hidden");
    if (!editForm.classList.contains("hidden")) {
      editInput.focus();
    }
  });

  cancelTargetButton.addEventListener("click", () => {
    editForm.classList.add("hidden");
    editInput.value = String(product.target_price);
  });

  saveTargetButton.addEventListener("click", async () => {
    const newTarget = parseFloat(editInput.value);
    if (!Number.isFinite(newTarget) || newTarget <= 0) {
      say("Enter a valid target price greater than 0.", "err");
      return;
    }

    saveTargetButton.disabled = true;
    try {
      const updated = await api(API.update(product.id), {
        method: "PUT",
        body: JSON.stringify({ target_price: newTarget })
      });

      product.target_price = updated.target_price;
      item.querySelector(".target-val").textContent = money(updated.target_price, sym);

      const freshCur = Number(product.current_price);
      const newHit = freshCur <= updated.target_price;
      if (newHit) {
        item.dataset.hit = "";
      } else {
        delete item.dataset.hit;
      }

      const statusBadge = item.querySelector(".status-badge");
      statusBadge.dataset.variant = newHit ? "warn" : "outline";
      statusBadge.textContent = newHit ? "Target reached" : "Watching";

      editForm.classList.add("hidden");
      say(`Target price updated to ${money(updated.target_price, sym)}.`, "ok");
    } catch (error) {
      console.error("Update target price failed:", error);
      say(error.message, "err");
    } finally {
      saveTargetButton.disabled = false;
    }
  });

  // 4. View Price History
  historyButton.addEventListener("click", async () => {
    const willShow = historyPanel.classList.contains("hidden");
    historyPanel.classList.toggle("hidden");

    if (!willShow) return;
    loadCardHistory();
  });

  // Export this item's history
  exportHistoryItemBtn.addEventListener("click", async () => {
    await downloadCsv(
      API.exportHistory(getEmail(), product.id),
      `pricehawk_history_product_${product.id}.csv`
    );
  });

  // 5. Demo Price Simulation (Drop price below target)
  if (simulateButton) {
    simulateButton.addEventListener("click", async () => {
      const currentTarget = Number(product.target_price);
      const droppedPrice = Math.max(1, Math.round((currentTarget - 1.0) * 100) / 100);

      simulateButton.disabled = true;
      say("Simulating price drop in Demo Mode...");

      try {
        const result = await api(API.simulate(product.id), {
          method: "POST",
          body: JSON.stringify({ price: droppedPrice })
        });

        console.log("Simulate result:", result);
        const freshPrice = Number(result.current_price);
        const latestTarget = Number(
          result.target_price !== undefined ? result.target_price : product.target_price
        );

        product.current_price = freshPrice;
        product.target_price = latestTarget;
        product.alert_sent = Boolean(result.alert_sent);
        product.last_checked_at = result.last_checked_at;

        item.querySelector(".now").textContent = money(freshPrice, sym);
        item.dataset.hit = "";

        const statusBadge = item.querySelector(".status-badge");
        statusBadge.dataset.variant = "warn";
        statusBadge.textContent = "Target reached";

        if (!historyPanel.classList.contains("hidden")) {
          loadCardHistory();
        }

        say(`Demo drop: simulated ${money(freshPrice, sym)}. Target reached!`, "ok");
      } catch (error) {
        console.error("Simulation failed:", error);
        say(error.message, "err");
      } finally {
        simulateButton.disabled = false;
      }
    });
  }

  // 6. Remove Product from Tracking
  removeButton.addEventListener("click", async () => {
    const confirmed = confirm(
      `Remove "${product.title || "this product"}" from tracking?`
    );

    if (!confirmed) return;

    removeButton.disabled = true;

    try {
      await api(API.remove(product.id), { method: "DELETE" });

      // Immediate DOM removal prevents stale card display
      item.remove();

      say("Product removed from tracking.", "ok");

      const remaining = document.querySelectorAll("#items .item").length;
      $("count").textContent = String(remaining);

      if (remaining === 0) {
        $("empty").classList.remove("hidden");
      }

      loadList().catch(() => {});
      refreshCount().catch(() => {});
    } catch (error) {
      console.error("PriceHawk product removal failed:", error);
      say(error.message, "err");
      removeButton.disabled = false;
    }
  });

  return item;
}

// =====================================================
// REFRESH TRACKED PRODUCT COUNT
// =====================================================

async function refreshCount() {
  const email = getEmail();
  if (!isValidEmail(email)) {
    $("count").textContent = "0";
    return;
  }

  try {
    const data = await api(API.list(email));
    const products = Array.isArray(data.products) ? data.products : [];
    $("count").textContent = String(products.length);
  } catch (error) {
    console.error("PriceHawk count refresh failed:", error);
  }
}

// =====================================================
// CSV EXPORT HELPERS
// =====================================================

async function downloadCsv(url, defaultFilename) {
  if (!isValidEmail()) {
    say("Enter a valid notification email before exporting.", "err");
    return;
  }

  try {
    say("Preparing CSV download...");
    const response = await fetch(url);

    if (!response.ok) {
      let message = `Export failed (${response.status}).`;
      try {
        const data = await response.json();
        message = data.error || data.message || message;
      } catch {
        // Retain default message
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = downloadUrl;
    link.download = defaultFilename;

    document.body.appendChild(link);
    link.click();
    link.remove();

    setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
    say("Export downloaded successfully.", "ok");
  } catch (error) {
    console.error("PriceHawk export failed:", error);
    say(error.message, "err");
  }
}

// Export products to CSV
$("exportBtn").addEventListener("click", () => {
  downloadCsv(API.export(getEmail()), "pricehawk_products.csv");
});

// Export all price history to CSV
$("exportHistoryBtn").addEventListener("click", () => {
  downloadCsv(API.exportHistory(getEmail()), "pricehawk_history.csv");
});

// When email input changes, save to localStorage and refresh if valid
$("email").addEventListener("input", () => {
  const val = getEmail();
  if (isValidEmail(val)) {
    saveEmail(val);
    refreshCount();
    if (!$("view-list").classList.contains("hidden")) {
      loadList();
    }
  }
});

// =====================================================
// INITIALIZATION
// =====================================================

async function initialize() {
  console.log("PriceHawk initialization started");

  loadSavedEmail();

  try {
    const detectionPromise = detect();
    await testBackendConnection();
    await detectionPromise;

    if (isValidEmail()) {
      await refreshCount();
    }

    console.log("PriceHawk initialization completed");
  } catch (error) {
    console.error("PriceHawk initialization error:", error);
    say(error.message || "PriceHawk could not initialize.", "err");
  }
}

initialize();