/** Sanitize wire page context — strip nulls from browser/Playwright payloads. */

import type { PageContextWire } from "./observation.js";

export function sanitizePageContextWire(
  context: PageContextWire,
): PageContextWire {
  return {
    title: context.title ?? "",
    url: context.url ?? "",
    elements: (context.elements ?? []).map((el) => {
      const row: PageContextWire["elements"][number] = {
        index: el.index,
        role: el.role,
        tag: el.tag,
        text: el.text ?? "",
        placeholder: el.placeholder ?? "",
        ariaLabel: el.ariaLabel ?? "",
      };
      if (el.href) row.href = el.href;
      if (el.value) row.value = el.value;
      if (el.enabled != null) row.enabled = el.enabled;
      if (el.bboxX != null) row.bboxX = el.bboxX;
      if (el.bboxY != null) row.bboxY = el.bboxY;
      if (el.bboxWidth != null) row.bboxWidth = el.bboxWidth;
      if (el.bboxHeight != null) row.bboxHeight = el.bboxHeight;
      return row;
    }),
    products: context.products,
    cartLines: context.cartLines,
    screenshotDataUrl: context.screenshotDataUrl,
  };
}
