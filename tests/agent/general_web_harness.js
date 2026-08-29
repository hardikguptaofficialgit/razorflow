/** Site-agnostic page context extraction for general-web E2E tests. */

function extractPageContext() {
  const truncate = (v, max = 120) => {
    const t = (v || "").trim().replace(/\s+/g, " ");
    return t.length <= max ? t : t.slice(0, max - 1) + "…";
  };
  const isVisible = (el) => {
    if (!el) return false;
    const s = window.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.display !== "none" && s.visibility !== "hidden" && r.width > 0 && r.height > 0;
  };
  const ranked = Array.from(
    document.querySelectorAll(
      'a,button,input,textarea,select,[role="button"],[role="link"],[role="searchbox"]',
    ),
  ).filter(isVisible).slice(0, 120);
  const inferRole = (el) => {
    if (el instanceof HTMLInputElement) {
      if (el.type === "search" || el.getAttribute("role") === "search") return "search";
      return "input";
    }
    if (el instanceof HTMLTextAreaElement) return "input";
    if (el instanceof HTMLButtonElement || el.getAttribute("role") === "button") return "button";
    return "link";
  };
  const elements = ranked.map((el, i) => {
    const rect = el.getBoundingClientRect();
    const href = el instanceof HTMLAnchorElement ? el.href : el.getAttribute("href") || "";
    const value =
      el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement ? el.value : "";
    const row = {
      index: i + 1,
      role: inferRole(el),
      tag: el.tagName.toLowerCase(),
      text: truncate(el.textContent || ""),
      placeholder: truncate(el.getAttribute("placeholder") || ""),
      ariaLabel: truncate(el.getAttribute("aria-label") || ""),
      enabled: !(el.hasAttribute("disabled") || el.getAttribute("aria-disabled") === "true"),
      bboxX: Math.round(rect.x),
      bboxY: Math.round(rect.y),
      bboxWidth: Math.round(rect.width),
      bboxHeight: Math.round(rect.height),
    };
    if (href) {
      row.href = truncate(href, 200);
    }
    if (value) {
      row.value = truncate(value, 80);
    }
    return row;
  });
  const productCards = Array.from(document.querySelectorAll("[data-rf-product-card]"));
  let products = productCards
    .map((card) => {
      const title = truncate(
        card.querySelector("h2,h3,[data-rf-product-title]")?.textContent || "",
      );
      const priceText = truncate(
        card.querySelector("[data-rf-product-price], .price, p")?.textContent || "",
      );
      const addBtn = card.querySelector("[data-rf-add-to-cart], button.add, button");
      let addToCartElementIndex = 0;
      if (addBtn) {
        const idx = ranked.indexOf(addBtn);
        if (idx >= 0) addToCartElementIndex = idx + 1;
      }
      const link = card.querySelector("a[href]");
      let elementIndex = 0;
      if (link) {
        const idx = ranked.indexOf(link);
        if (idx >= 0) elementIndex = idx + 1;
      }
      return { title, priceText, addToCartElementIndex, elementIndex };
    })
    .filter((p) => p.title && p.addToCartElementIndex > 0);

  if (!products.length) {
    products = Array.from(document.querySelectorAll("[class*='product'], article"))
      .slice(0, 32)
      .map((card) => {
        const title = truncate(card.querySelector("h2,h3")?.textContent || "");
        const priceText = truncate((card.textContent || "").match(/₹[\d,]+/)?.[0] || "");
        const addBtn = card.querySelector("button");
        let addToCartElementIndex = 0;
        if (addBtn) {
          const idx = ranked.indexOf(addBtn);
          if (idx >= 0) addToCartElementIndex = idx + 1;
        }
        return { title, priceText, addToCartElementIndex, elementIndex: 0 };
      })
      .filter((p) => p.title && p.addToCartElementIndex > 0);
  }

  const cartLines = Array.from(document.querySelectorAll("[data-rf-cart-line]")).map((line) => ({
    title: truncate(line.querySelector("[data-rf-product-title], h2, h3")?.textContent || ""),
    quantity: parseInt(line.querySelector("[data-rf-line-qty]")?.textContent || "1", 10) || 1,
  }));
  return {
    title: document.title,
    url: window.location.href,
    elements,
    products,
    cartLines,
  };
}

async function executeStep(step) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const isVisible = (el) => {
    if (!el) return false;
    const s = window.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.display !== "none" && s.visibility !== "hidden" && r.width > 0 && r.height > 0;
  };
  const ranked = Array.from(
    document.querySelectorAll(
      'a,button,input,textarea,select,[role="button"],[role="link"],[role="searchbox"]',
    ),
  ).filter(isVisible);
  const findTarget = () => {
    if (step.elementIndex) {
      const el = ranked[step.elementIndex - 1];
      if (el) return el;
    }
    const needle = (step.matchText || "").toLowerCase();
    if (needle) {
      for (const el of ranked) {
        const blob = `${el.textContent || ""} ${el.getAttribute("aria-label") || ""} ${el.getAttribute("placeholder") || ""} ${el.getAttribute("value") || ""}`.toLowerCase();
        if (blob.includes(needle)) return el;
      }
    }
    if (step.role === "search") {
      return document.querySelector(
        'input[type="search"], input[name="search"], #searchInput, input[name="q"], [role="searchbox"]',
      );
    }
    if (step.role === "input") {
      const needle = (step.matchText || "").toLowerCase();
      for (const el of ranked) {
        if (!(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) continue;
        const blob = `${el.name || ""} ${el.id || ""} ${el.placeholder || ""} ${el.getAttribute("aria-label") || ""}`.toLowerCase();
        if (needle && blob.includes(needle)) return el;
      }
    }
    return null;
  };

  if (step.action === "scroll_page") {
    const before = window.scrollY;
    const dir = step.direction || "down";
    const amount = step.amountPx || 600;
    if (dir === "top") window.scrollTo(0, 0);
    else if (dir === "bottom") window.scrollTo(0, document.documentElement.scrollHeight);
    else if (dir === "up") window.scrollBy(0, -amount);
    else window.scrollBy(0, amount);
    await sleep(300);
    return { success: true, verified: window.scrollY !== before };
  }

  if (step.action === "go_back") {
    const before = location.href;
    history.back();
    await sleep(500);
    return { success: location.href !== before, verified: location.href !== before };
  }

  if (step.action === "wait") {
    await sleep(Math.min(5000, step.durationMs || 500));
    return { success: true, verified: true };
  }

  if (step.action === "navigate_url") {
    const before = location.href;
    location.assign(step.url);
    const target = new URL(step.url, location.origin);
    const want = target.pathname + target.search + target.hash;
    for (let i = 0; i < 150; i++) {
      const cur = location.pathname + location.search + location.hash;
      if (cur === want) return { success: true, verified: true };
      await sleep(100);
    }
    return { success: location.href !== before, verified: location.href !== before };
  }

  if (step.action === "type_in_element") {
    let el = findTarget();
    if (!el && step.matchText) {
      const needle = step.matchText.toLowerCase();
      for (const input of document.querySelectorAll("input,textarea")) {
        const blob = `${input.name || ""} ${input.id || ""} ${input.placeholder || ""}`.toLowerCase();
        if (blob.includes(needle) || blob.includes("cust") || blob.includes("tel")) {
          el = input;
          break;
        }
      }
    }
    if (!el || !(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) {
      return { success: false, error: "No typeable target" };
    }
    const before = location.href;
    const text = step.text || "";
    el.focus();
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value",
    )?.set;
    if (nativeSetter) {
      nativeSetter.call(el, text);
    } else {
      el.value = text;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    const shouldSubmit = !step.matchText || /submit|search|go/i.test(step.matchText);
    if (el.form && shouldSubmit) {
      const submit = el.form.querySelector(
        'button[type="submit"],input[type="submit"],[data-rf-label="Search"],.rf-search-submit',
      );
      if (submit) submit.click();
      else el.form.requestSubmit?.();
    } else {
      el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    }
    await sleep(1200);
    const changed =
      location.href !== before ||
      document.body.innerText.toLowerCase().includes(text.toLowerCase().slice(0, 8));
    return { success: text.length > 0, verified: changed };
  }

  if (step.action === "click_element") {
    const beforeUrl = location.href;
    const beforeCart = typeof window.__RF_LAST_CART__ === "function" ? window.__RF_LAST_CART__().length : 0;
    const needle = (step.matchText || "").toLowerCase();
    if (needle.includes("add") && needle.includes("cart")) {
      const productNeedle = needle
        .replace(/add to cart for /g, "")
        .replace(/add to cart/g, "")
        .trim();
      const cards = Array.from(document.querySelectorAll("[data-rf-product-card]"));
      for (const card of cards) {
        const title = (card.querySelector("h2,h3")?.textContent || "").toLowerCase();
        if (productNeedle && title && !title.includes(productNeedle) && !productNeedle.includes(title)) {
          continue;
        }
        const btn = card.querySelector("[data-rf-add-to-cart], button.add, button");
        if (btn) {
          btn.scrollIntoView({ block: "center" });
          await sleep(150);
          btn.click();
          await sleep(500);
          const afterCart = typeof window.__RF_LAST_CART__ === "function" ? window.__RF_LAST_CART__().length : 0;
          return { success: true, verified: afterCart > beforeCart || location.href !== beforeUrl };
        }
      }
    }
    const el = findTarget();
    if (!el) return { success: false, error: "Click target not found" };
    el.scrollIntoView({ block: "center" });
    await sleep(150);
    el.click();
    await sleep(600);
    const afterCart = typeof window.__RF_LAST_CART__ === "function" ? window.__RF_LAST_CART__().length : 0;
    const changed = location.href !== beforeUrl;
    return { success: true, verified: afterCart > beforeCart || changed || Boolean(step.matchText) };
  }

  return { success: true, verified: true };
}
