// Visual helpers only: price label, quick-target buttons, progress meter.
// No backend calls here. Your popup.js can use window.PriceHawkUI.

(function () {
    const priceEl = document.getElementById("current-price");
    const targetEl = document.getElementById("target-price");
    const fill = document.getElementById("gap-fill");
    const gapText = document.getElementById("gap-text");
    const toggles = document.querySelectorAll(".toggle-item");

    let price = null;   // number, e.g. 51.77
    let symbol = "£";

    function setPrice(text) {
        const match = String(text).match(/([^\d\s.,-]*)\s*(\d+)(?:[.,](\d{1,2}))?/);
        if (!match) return;
        symbol = match[1] || symbol;
        const whole = match[2];
        const pence = (match[3] || "00").padEnd(2, "0");
        price = parseFloat(whole + "." + pence);
        priceEl.innerHTML =
            '<span class="price-currency"></span><span class="price-whole"></span><sup class="price-pence"></sup>';
        priceEl.querySelector(".price-currency").textContent = symbol;
        priceEl.querySelector(".price-whole").textContent = whole;
        priceEl.querySelector(".price-pence").textContent = pence;
        updateGap();
    }

    function updateGap() {
        const target = parseFloat(targetEl.value);
        if (!price || !target || target <= 0) {
            fill.style.setProperty("--progress", "0%");
            gapText.textContent = "Set a target to see how far away it is.";
            return;
        }
        if (target >= price) {
            fill.style.setProperty("--progress", "100%");
            gapText.textContent = "Already at or below your target.";
            return;
        }
        fill.style.setProperty("--progress", Math.round((target / price) * 100) + "%");
        gapText.textContent = symbol + (price - target).toFixed(2) + " to drop";
    }

    toggles.forEach((btn) => {
        btn.addEventListener("click", () => {
            if (!price) return;
            const wasOn = btn.getAttribute("aria-pressed") === "true";
            toggles.forEach((b) => b.setAttribute("aria-pressed", "false"));
            if (wasOn) { targetEl.value = ""; }
            else {
                btn.setAttribute("aria-pressed", "true");
                targetEl.value = (price * (1 - Number(btn.dataset.discount) / 100)).toFixed(2);
            }
            updateGap();
        });
    });

    targetEl.addEventListener("input", () => {
        toggles.forEach((b) => b.setAttribute("aria-pressed", "false"));
        updateGap();
    });

    // message helper: PriceHawkUI.showMessage("Saved", "success")
    function showMessage(text, kind) {
        const el = document.getElementById("message");
        el.textContent = text || "";
        el.className = "message" + (kind ? " " + kind : "");
    }

    window.PriceHawkUI = { setPrice, updateGap, showMessage };
    const w = priceEl.querySelector(".price-whole");
    const c = priceEl.querySelector(".price-pence");
    setPrice(w && c ? symbol + w.textContent + "." + c.textContent : priceEl.textContent);
})();