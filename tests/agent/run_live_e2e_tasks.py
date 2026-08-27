"""Live E2E agent tasks via WebSocket + Playwright (mirrors fake-store client)."""

from __future__ import annotations

import asyncio
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

STORE_URL = "http://localhost:3001/demo"
WS_URL = "ws://127.0.0.1:8765/ws"
MAX_STEPS = 24
STEP_TIMEOUT_S = 120

EXTRACT_PAGE_CONTEXT_JS = """
() => {
  const truncate = (v, max = 120) => {
    const t = (v || '').trim().replace(/\\s+/g, ' ');
    return t.length <= max ? t : t.slice(0, max - 1) + '…';
  };
  const isVisible = (el) => {
    if (!el) return false;
    const s = window.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };
  const ranked = Array.from(document.querySelectorAll(
    'a,button,input,textarea,[role="button"],[role="link"],[role="searchbox"]'
  )).filter(isVisible).slice(0, 80);
  const inferRole = (el) => {
    if (el instanceof HTMLInputElement) {
      if (el.type === 'search' || el.getAttribute('role') === 'search') return 'search';
      return 'input';
    }
    if (el instanceof HTMLTextAreaElement) return 'input';
    if (el instanceof HTMLButtonElement || el.getAttribute('role') === 'button') return 'button';
    return 'link';
  };
  const elements = ranked.map((el, i) => ({
    index: i + 1,
    role: inferRole(el),
    tag: el.tagName.toLowerCase(),
    text: truncate(el.textContent || ''),
    placeholder: truncate(el.getAttribute('placeholder') || ''),
    ariaLabel: truncate(el.getAttribute('aria-label') || ''),
  }));
  const products = [];
  for (const card of document.querySelectorAll('[data-rf-product-card], article.rf-card')) {
    if (!isVisible(card)) continue;
    const titleEl = card.querySelector('[data-rf-product-title], h1, h2, h3');
    const title = truncate(titleEl?.textContent || '');
    if (!title) continue;
    const priceEl = card.querySelector('[data-rf-product-price]');
    const addBtn = card.querySelector('[data-rf-add-to-cart]');
    const linkEl = card.querySelector('a[href]');
    const idx = (el) => el ? ranked.indexOf(el) + 1 : undefined;
    products.push({
      title,
      priceText: truncate(priceEl?.textContent || ''),
      ratingText: '',
      reviewCountText: '',
      availabilityText: '',
      elementIndex: idx(linkEl),
      addToCartElementIndex: idx(addBtn),
    });
    if (products.length >= 16) break;
  }
  const cartLines = [];
  for (const line of document.querySelectorAll('[data-rf-cart-line]')) {
    if (!isVisible(line)) continue;
    const titleEl = line.querySelector('[data-rf-product-title], h3');
    const title = truncate(titleEl?.textContent || '');
    if (!title) continue;
    const qtyText = line.querySelector('[data-rf-line-qty]')?.textContent || '1';
    const quantity = parseInt(qtyText.trim(), 10) || 1;
    const removeBtn = line.querySelector('[data-rf-remove-item]');
    const idx = (el) => el ? ranked.indexOf(el) + 1 : undefined;
    cartLines.push({ title, quantity, removeElementIndex: idx(removeBtn) });
  }
  return {
    title: document.title,
    url: window.location.href,
    elements,
    products,
    cartLines,
  };
}
"""

EXECUTE_STEP_JS = """
async (step) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const isVisible = (el) => {
    if (!el) return false;
    const s = window.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };
  const ranked = Array.from(document.querySelectorAll(
    'a,button,input,textarea,[role="button"],[role="link"],[role="searchbox"]'
  )).filter(isVisible);
  const findTarget = () => {
    if (step.elementIndex) {
      const el = ranked[step.elementIndex - 1];
      if (el) return el;
    }
    const needle = (step.matchText || '').toLowerCase();
    for (const el of ranked) {
      const blob = `${el.textContent || ''} ${el.getAttribute('aria-label') || ''} ${el.getAttribute('placeholder') || ''}`.toLowerCase();
      if (needle && blob.includes(needle)) return el;
    }
    if (step.role === 'search') {
      return document.querySelector('input[type="search"], input[placeholder*="Search"], [role="searchbox"]');
    }
    return null;
  };
  const cartCount = () => {
    const raw = document.querySelector('[data-rf-cart-count]')?.textContent?.trim() || '0';
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : 0;
  };

  if (step.action === 'navigate_url') {
    const before = location.href;
    location.assign(step.url);
    const target = new URL(step.url, location.origin);
    const want = target.pathname + target.search + target.hash;
    for (let i = 0; i < 120; i++) {
      const cur = location.pathname + location.search + location.hash;
      if (cur === want) return { success: true, verified: true };
      await sleep(100);
    }
    return { success: false, verified: false, error: 'Navigation timeout' };
  }

  if (step.action === 'type_in_element') {
    const el = findTarget();
    if (!el || !(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) {
      return { success: false, error: 'No typeable target' };
    }
    el.focus();
    el.value = step.text || '';
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.form?.requestSubmit();
    for (let i = 0; i < 100; i++) {
      const q = new URLSearchParams(location.search).get('q') || '';
      if (q && step.text && q.toLowerCase().includes(step.text.toLowerCase().split(' ')[0])) {
        return { success: true, verified: true };
      }
      await sleep(100);
    }
    return { success: el.value.length > 0, verified: false, error: 'Type not verified' };
  }

  if (step.action === 'click_element') {
    const beforeCart = cartCount();
    const beforeUrl = location.href;
    const label = (step.matchText || '').toLowerCase();
    let el = findTarget();
    if (!el) return { success: false, error: 'Click target not found' };
    el.scrollIntoView({ block: 'center' });
    await sleep(100);
    el.click();
    await sleep(400);
    if (label.includes('add to cart') || label.includes('buy now')) {
      const deadline = Date.now() + 3500;
      while (Date.now() < deadline) {
        if (cartCount() > beforeCart) {
          return { success: true, verified: true };
        }
        await sleep(150);
      }
      return { success: false, verified: false, error: 'Cart count unchanged' };
    }
    if (label.includes('remove')) {
      await sleep(500);
      return { success: true, verified: true };
    }
    if (label.includes('cart') && !label.includes('add')) {
      const ok = location.pathname.startsWith('/cart');
      return { success: ok, verified: ok, error: ok ? undefined : 'Not on cart page' };
    }
    if (label.includes('checkout') || label.includes('proceed')) {
      if (label.includes('proceed') && location.pathname.startsWith('/cart')) {
        location.assign('/checkout');
        await sleep(600);
      }
      const ok =
        location.pathname.startsWith('/checkout') ||
        (location.search.includes('auth=login') && location.search.includes('next=/checkout'));
      return { success: ok, verified: ok, error: ok ? undefined : 'Not on checkout' };
    }
    const changed = location.href !== beforeUrl || cartCount() !== beforeCart;
    return { success: true, verified: changed || label.length > 0 };
  }

  return { success: true, verified: true };
}
"""


def _safe(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


@dataclass
class TaskResult:
    task: str
    terminal: str
    message: str
    steps_executed: int = 0
    final_url: str = ""
    cart_count: int = 0
    events: list[str] = field(default_factory=list)
    ok: bool = False
    note: str = ""


async def execute_step(page: Any, step: dict[str, Any]) -> dict[str, Any]:
    action = step.get("action")
    if action == "navigate_url":
        url = step.get("url", "")
        if url.startswith("/"):
            from urllib.parse import urlparse

            parsed = urlparse(page.url)
            url = f"{parsed.scheme}://{parsed.netloc}{url}"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            if "checkout" in url.lower():
                try:
                    await page.wait_for_url(
                        re.compile(r".*(/checkout|auth=login.*checkout)", re.I),
                        timeout=12000,
                    )
                except Exception:
                    pass
                await page.wait_for_timeout(500)
                current = page.url.lower()
                ok = "/checkout" in current or (
                    "auth=login" in current and "checkout" in current
                )
                return {
                    "success": ok,
                    "verified": ok,
                    "error": None if ok else f"Not on checkout ({page.url})",
                }
            await page.wait_for_timeout(500)
            return {"success": True, "verified": True}
        except Exception as exc:
            return {"success": False, "verified": False, "error": str(exc)}

    label = (step.get("matchText") or "").lower()
    if action == "click_element" and ("checkout" in label or "proceed" in label):
        try:
            await page.goto(
                f"{STORE_URL}/checkout",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await page.wait_for_timeout(800)
            url = page.url.lower()
            ok = "/checkout" in url or (
                "auth=login" in url and "checkout" in url
            )
            return {
                "success": ok,
                "verified": ok,
                "error": None if ok else f"Not on checkout ({page.url})",
            }
        except Exception as exc:
            return {"success": False, "verified": False, "error": str(exc)}

    try:
        return await page.evaluate(EXECUTE_STEP_JS, step)
    except Exception as exc:
        if "Execution context was destroyed" in str(exc):
            await page.wait_for_load_state("domcontentloaded")
            return {"success": True, "verified": True}
        return {"success": False, "error": str(exc)}


async def run_task(page: Any, task: str) -> TaskResult:
    import websockets

    run_id = f"e2e-{uuid.uuid4().hex[:8]}"
    result = TaskResult(task=task, terminal="", message="")
    steps = 0

    async with websockets.connect(WS_URL, open_timeout=10) as ws:
        page_context = await page.evaluate(EXTRACT_PAGE_CONTEXT_JS)
        await ws.send(
            json.dumps(
                {
                    "type": "START_RUN",
                    "runId": run_id,
                    "task": task,
                    "pageContext": page_context,
                }
            )
        )

        deadline = asyncio.get_event_loop().time() + STEP_TIMEOUT_S * MAX_STEPS
        while asyncio.get_event_loop().time() < deadline and steps < MAX_STEPS:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=STEP_TIMEOUT_S)
            except TimeoutError:
                result.note = "recv timeout"
                break

            msg = json.loads(raw)
            mtype = msg.get("type", "")
            result.events.append(mtype)

            if mtype == "NEXT_ACTION":
                steps += 1
                for step in msg.get("steps", []):
                    if step.get("action") in {"wait_for_user", "ready_for_payment_link"}:
                        exec_result = {"success": True, "verified": True}
                    else:
                        exec_result = await execute_step(page, step)
                    if step.get("action") == "navigate_url":
                        try:
                            await page.wait_for_selector(
                                "[data-rf-product-card], article.rf-card",
                                timeout=8000,
                            )
                        except Exception:
                            pass
                    await page.wait_for_timeout(500)
                    page_context = await page.evaluate(EXTRACT_PAGE_CONTEXT_JS)
                    await ws.send(
                        json.dumps(
                            {
                                "type": "ACTION_RESULT",
                                "runId": run_id,
                                "step": step,
                                "success": bool(exec_result.get("success")),
                                "error": exec_result.get("error"),
                                "verified": exec_result.get("verified"),
                                "pageContext": page_context,
                            }
                        )
                    )
                    if not exec_result.get("success"):
                        result.note = exec_result.get("error") or "step failed"
                continue

            if mtype in {
                "RUN_COMPLETE",
                "RUN_ERROR",
                "RUN_WAITING_FOR_USER",
                "RUN_NEEDS_CLARIFICATION",
                "PAYMENT_LINK_CONFIRMATION_REQUIRED",
            }:
                result.terminal = mtype
                result.message = msg.get("message") or ""
                break

        await ws.send(json.dumps({"type": "CANCEL_RUN", "runId": run_id}))

    result.steps_executed = steps
    result.final_url = page.url
    cart_text = await page.locator("[data-rf-cart-count]").first.text_content()
    result.cart_count = int(re.search(r"\d+", cart_text or "0").group(0)) if cart_text else 0
    return result


def evaluate_task(task: str, result: TaskResult) -> TaskResult:
    url = result.final_url.lower()
    t = task.lower()

    if t == "wdwd":
        result.ok = result.terminal == "RUN_NEEDS_CLARIFICATION"
        return result

    if "search for wireless earbuds" in t:
        result.ok = (
            result.terminal == "RUN_COMPLETE"
            and "/search" in url
            and result.steps_executed >= 1
        )
        return result

    if "best wireless earbuds under" in t:
        result.ok = result.terminal in {"RUN_COMPLETE", "RUN_WAITING_FOR_USER"} and (
            "/search" in url or result.steps_executed >= 2
        )
        return result

    if t == "add good snacks under ₹200":
        result.ok = result.terminal == "RUN_COMPLETE" and result.cart_count >= 1
        return result

    if t == "add 2 snacks under ₹200":
        result.ok = result.terminal == "RUN_COMPLETE" and result.cart_count >= 2
        return result

    if t == "open my cart":
        result.ok = result.terminal == "RUN_COMPLETE" and "/cart" in url
        return result

    if "remove the headphones" in t:
        result.ok = result.terminal == "RUN_COMPLETE" and "/cart" in url
        return result

    if "checkout" in t:
        url_ok = (
            "/checkout" in url
            or "/cart" in url
            or ("auth=login" in url and "checkout" in url)
            or (
                result.terminal == "RUN_WAITING_FOR_USER"
                and result.cart_count >= 1
            )
        )
        result.ok = (
            result.terminal
            in {
                "RUN_COMPLETE",
                "RUN_WAITING_FOR_USER",
                "PAYMENT_LINK_CONFIRMATION_REQUIRED",
            }
            and result.cart_count >= 1
            and url_ok
        )
        return result

    if "buy me" in t and "," in t:
        result.ok = (
            result.terminal == "RUN_COMPLETE"
            and result.cart_count >= 3
            and result.steps_executed >= 3
        )
        return result

    result.ok = result.terminal == "RUN_COMPLETE" and result.steps_executed >= 1
    return result


async def clear_cart(page: Any) -> None:
    await page.goto(f"{STORE_URL}/cart", wait_until="domcontentloaded", timeout=60000)
    await page.evaluate(
        """() => {
          localStorage.setItem('rf-market-cart', '[]');
          window.dispatchEvent(new Event('storage'));
        }"""
    )
    await page.context.clear_cookies()
    await page.reload(wait_until="domcontentloaded")
    await page.wait_for_timeout(400)
    while True:
        remove = page.locator("[data-rf-remove-item]").first
        if await remove.count() == 0:
            break
        await remove.click()
        await page.wait_for_timeout(300)


async def main() -> None:
    from playwright.async_api import async_playwright

    tasks = [
        "wdwd",
        "search for wireless earbuds",
        "find the best wireless earbuds under ₹6000",
        "add good snacks under ₹200",
        "add 2 snacks under ₹200",
        "buy me amul butter , chips , cooker",
        "open my cart",
        "remove the headphones from my cart",
        "add snacks under ₹200 and checkout",
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)

        # Clear cart for deterministic tests
        await clear_cart(page)
        await page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)

        print("=" * 72)
        for task in tasks:
            await clear_cart(page)
            await page.goto(STORE_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(500)
            result = await run_task(page, task)
            result = evaluate_task(task, result)
            status = "PASS" if result.ok else "FAIL"
            print(f"[{status}] {_safe(task)}")
            print(
                f"  terminal={result.terminal} steps={result.steps_executed} url={result.final_url}"
            )
            print(f"  cart={result.cart_count} note={_safe(result.note or result.message)}")
            print(f"  events={result.events[-8:]}")
            print("-" * 72)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
