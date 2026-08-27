"""CDP cart-count helper shared by runner and tools."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def read_cart_count(browser_session: Any | None) -> int | None:
    """Best-effort cart item count from the live page (None if unknown)."""
    if browser_session is None:
        return None
    try:
        cdp_session = await browser_session.get_or_create_cdp_session(focus=False)
        script = """
        (() => {
          try {
            const raw = window.localStorage.getItem('rf-market-cart');
            if (raw) {
              const items = JSON.parse(raw);
              if (Array.isArray(items)) {
                const count = items.reduce((sum, line) => {
                  const qty = Number(line?.quantity ?? 0);
                  return sum + (Number.isFinite(qty) ? qty : 0);
                }, 0);
                if (count > 0) return count;
              }
            }
          } catch (_) {}

          const text = document.body ? document.body.innerText : '';
          const aria = Array.from(document.querySelectorAll('[aria-label]'))
            .map(el => el.getAttribute('aria-label') || '')
            .join(' ');
          const blob = (text + ' ' + aria).toLowerCase();
          const patterns = [
            /cart,?\\s*(\\d+)\\s*items?/,
            /(\\d+)\\s*items?\\s*in\\s*cart/,
            /cart\\s*\\((\\d+)\\)/,
          ];
          for (const re of patterns) {
            const m = blob.match(re);
            if (m) return Number(m[1]);
          }

          const badge = document.querySelector('[data-cart-count], .rf-header-cart__badge, a[href*="/cart"]');
          if (badge) {
            const m2 = (badge.textContent || badge.getAttribute('aria-label') || '').match(/(\\d+)/);
            if (m2) return Number(m2[1]);
          }
          return null;
        })()
        """
        result = await cdp_session.cdp_client.send.Runtime.evaluate(
            params={"expression": script, "returnByValue": True},
            session_id=cdp_session.session_id,
        )
        value = None
        if result and "result" in result:
            value = result["result"].get("value")
        if isinstance(value, (int, float)):
            return int(value)
        return None
    except Exception as error:
        logger.debug("cart count read failed: %s", error)
        return None
