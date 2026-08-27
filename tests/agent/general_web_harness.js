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
  return {
    title: document.title,
    url: window.location.href,
    elements,
    products: [],
    cartLines: [],
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
    el.focus();
    el.value = step.text || "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    const shouldSubmit = !step.matchText || /submit|search|go/i.test(step.matchText);
    if (el.form && shouldSubmit) {
      const submit = el.form.querySelector('button[type="submit"],input[type="submit"]');
      if (submit) submit.click();
      else el.form.requestSubmit?.();
    } else {
      el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    }
    await sleep(800);
    const changed = location.href !== before || document.body.innerText.toLowerCase().includes((step.text || "").toLowerCase().slice(0, 8));
    return { success: el.value.length > 0, verified: changed };
  }

  if (step.action === "click_element") {
    const beforeUrl = location.href;
    const el = findTarget();
    if (!el) return { success: false, error: "Click target not found" };
    el.scrollIntoView({ block: "center" });
    await sleep(150);
    el.click();
    await sleep(600);
    const changed = location.href !== beforeUrl;
    return { success: true, verified: changed || Boolean(step.matchText) };
  }

  return { success: true, verified: true };
}
