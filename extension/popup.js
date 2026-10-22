// PriceHawk popup. API route names are assumptions; adjust API.* to match backend/app.py.
const API_BASE = "http://127.0.0.1:5000";
const API = {
  list: () => `${API_BASE}/api/products`,
  add: () => `${API_BASE}/api/products`,
  check: id => `${API_BASE}/api/products/${id}/check`,
  remove: id => `${API_BASE}/api/products/${id}`,
  export: () => `${API_BASE}/api/export/products.csv`,
};
const $ = id => document.getElementById(id);
const SUPPORTED_HOST = "books.toscrape.com";
let detected = null; // {title, price, url}

async function api(url, opts = {}) {
  try {
    const res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
  } catch (e) {
    if (e instanceof TypeError) throw new Error("Can't reach the PriceHawk backend. Start Flask on port 5000.");
    throw e;
  }
}

function say(text, kind = "") { const a = $("alert"); a.classList.toggle("hidden", !text); a.dataset.variant = kind === "err" ? "destructive" : "default"; $("alertText").textContent = text; }
function money(n) { return n == null ? "—" : "£" + Number(n).toFixed(2); }

function show(view) {
  document.querySelectorAll(".tabs-trigger").forEach(t => t.dataset.state = t.dataset.view === view ? "active" : "inactive");
  $("view-track").classList.toggle("hidden", view !== "track");
  $("view-list").classList.toggle("hidden", view !== "list");
  if (view === "list") loadList();
}
document.querySelectorAll("[data-view]").forEach(b => b.addEventListener("click", () => show(b.dataset.view)));

/* ---------- detection (reads the page DOM through activeTab + scripting) ---------- */
function readPage() {
  const title = document.querySelector(".product_main h1")?.textContent.trim();
  const price = document.querySelector(".product_main .price_color")?.textContent.replace(/[^0-9.]/g, "");
  return { title, price: price ? parseFloat(price) : null, url: location.href };
}
async function detect() {
  const st = $("detectStatus");
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const host = new URL(tab.url).hostname;
    if (host !== SUPPORTED_HOST) throw new Error("unsupported");
    const [{ result }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: readPage });
    if (!result.title) throw new Error("no product");
    detected = result;
    $("pTitle").textContent = result.title;
    $("pPrice").textContent = money(result.price);
    $("pUrl").textContent = result.url;
    $("detectText").textContent = "Product detected";
    st.dataset.state = "ok";
  } catch {
    $("detectText").textContent = "No product detected";
    st.dataset.state = "warn";
  }
  updateGauge();
}

function updateGauge() {
  const t = parseFloat($("target").value), p = detected?.price;
  const fill = $("gaugeFill");
  if (!t || !p) { fill.style.width = "0"; $("gaugeText").textContent = "Set a target"; return; }
  const pct = Math.min(100, (t / p) * 100);
  fill.style.width = pct + "%";
  fill.classList.toggle("hit", p <= t);
  $("gaugeText").textContent = p <= t ? "Already at target" : `${money(p - t)} to go`;
}
$("target").addEventListener("input", updateGauge);

$("manualToggle").addEventListener("click", () => {
  $("manualField").classList.toggle("hidden");
  $("manualToggle").textContent = $("manualField").classList.contains("hidden")
    ? "Enter a product link instead" : "Use the detected product";
});

/* ---------- track ---------- */
$("trackBtn").addEventListener("click", async () => {
  const target = parseFloat($("target").value);
  const manual = !$("manualField").classList.contains("hidden");
  const url = manual ? $("manualUrl").value.trim() : detected?.url;
  if (!url) return say("Open a product page or enter a link first.", "err");
  if (!(target > 0)) return say("Enter a target price above 0.", "err");
  $("trackBtn").disabled = true; $("trackSpin").classList.remove("hidden"); say("Starting tracking…");
  try {
    await api(API.add(), { method: "POST", body: JSON.stringify({ url, target_price: target }) });
    say("Tracking started. We'll email you at your target.", "ok");
    refreshCount();
  } catch (e) { say(e.message, "err"); }
  finally { $("trackBtn").disabled = false; $("trackSpin").classList.add("hidden"); }
});

/* ---------- tracked list ---------- */
async function loadList() {
  const ul = $("items"); ul.innerHTML = "";
  try {
    const items = await api(API.list());
    $("count").textContent = items.length;
    $("empty").querySelector(".empty-title").textContent = "Nothing tracked yet";
    $("empty").querySelector(".empty-desc").textContent = "Track a product and it will show up here.";
    $("empty").classList.toggle("hidden", items.length > 0);
    items.forEach(p => ul.appendChild(card(p)));
  } catch (e) {
    $("empty").classList.remove("hidden");
    $("empty").querySelector(".empty-title").textContent = "Can't load tracked products";
    $("empty").querySelector(".empty-desc").textContent = e.message;
  }
}
function card(p) {
  const hit = p.current_price <= p.target_price;
  const li = document.createElement("li");
  li.className = "card item";
  if (hit) li.dataset.hit = "";
  li.innerHTML = `<div class="card-header"><div class="card-title"></div>
      <span class="badge" data-variant="${hit ? "warn" : "outline"}">${hit ? "Target reached" : "Watching"}</span></div>
    <div class="row"><div><span class="muted">Current</span><strong class="now">${money(p.current_price)}</strong></div>
      <div><span class="muted">Target</span><strong>${money(p.target_price)}</strong></div></div>
    <div class="card-footer"><button class="btn" data-variant="outline" data-size="sm" data-a="check">Check now</button>
      <button class="btn" data-variant="ghost" data-size="sm" data-destructive data-a="del">Remove</button></div>`;
  li.querySelector(".card-title").textContent = p.title;
  li.querySelector('[data-a="check"]').onclick = async () => { await api(API.check(p.id), { method: "POST" }).catch(() => {}); loadList(); };
  li.querySelector('[data-a="del"]').onclick = async () => { await api(API.remove(p.id), { method: "DELETE" }).catch(() => {}); loadList(); };
  return li;
}
async function refreshCount() { try { $("count").textContent = (await api(API.list())).length; } catch {} }

$("exportBtn").addEventListener("click", () => chrome.tabs.create({ url: API.export() }));

detect(); refreshCount();