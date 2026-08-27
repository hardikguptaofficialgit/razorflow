import {
  MAX_PAGE_ELEMENTS,
  MAX_PAGE_PRODUCTS,
  MAX_SUMMARY_TEXT_LENGTH,
  type PageContext,
  type PageElementSummary,
  type PageProductSummary,
} from "../shared/page-context";
import { OVERLAY_ROOT_ID } from "../shared/types";
import { collectRankedInteractiveElements } from "./dom-targeting";

const PRICE_HINT = /(?:₹|Rs\.?|INR|\$)\s?[\d,]+(?:\.\d{2})?/i;
const RATING_HINT =
  /(\d(?:\.\d)?)\s*(?:out of\s*5|\/\s*5|\s*stars?)|★{3,5}|aria-label=["'][^"']*\d(?:\.\d)?\s*out of/i;
const PRODUCT_CLASS_HINT = /product|item-card|product-card|listing|s-result/i;

function truncate(value: string, max = MAX_SUMMARY_TEXT_LENGTH): string {
  const trimmed = value.trim().replace(/\s+/g, " ");
  if (trimmed.length <= max) {
    return trimmed;
  }

  return `${trimmed.slice(0, max - 1)}…`;
}

function isInsideOverlay(element: Element): boolean {
  return Boolean(element.closest(`#${OVERLAY_ROOT_ID}`));
}

function isVisible(element: HTMLElement): boolean {
  if (isInsideOverlay(element)) {
    return false;
  }

  const style = window.getComputedStyle(element);
  if (
    style.display === "none" ||
    style.visibility === "hidden" ||
    Number(style.opacity) === 0
  ) {
    return false;
  }

  const rect = element.getBoundingClientRect();
  return rect.width > 2 && rect.height > 2;
}

function toElementSummary(
  index: number,
  role: PageElementSummary["role"],
  tag: string,
  text: string,
  placeholder: string,
  ariaLabel: string,
): PageElementSummary {
  return {
    index,
    role,
    tag,
    text: truncate(text),
    placeholder: truncate(placeholder),
    ariaLabel: truncate(ariaLabel),
  };
}

function collectInteractiveElements(): PageElementSummary[] {
  return collectRankedInteractiveElements(MAX_PAGE_ELEMENTS).map((entry, position) =>
    toElementSummary(
      position + 1,
      entry.role,
      entry.metadata.tag,
      entry.metadata.text,
      entry.metadata.placeholder,
      entry.metadata.ariaLabel,
    ),
  );
}

function extractProductTitle(element: HTMLElement): string {
  const heading = element.querySelector(
    "h1,h2,h3,h4,[class*='title'],[class*='name'],.a-text-normal",
  );
  return truncate(heading?.textContent ?? element.textContent ?? "");
}

function extractRatingText(element: HTMLElement): string {
  const labeled = element.querySelector(
    "[aria-label*='out of'], [aria-label*='stars'], .a-icon-alt, [class*='rating']",
  );
  const fromLabel = labeled?.getAttribute("aria-label") ?? labeled?.textContent ?? "";
  const match = fromLabel.match(RATING_HINT) ?? element.textContent?.match(RATING_HINT);
  return truncate(match?.[0] ?? fromLabel, 40);
}

function extractReviewCountText(element: HTMLElement): string {
  const text = element.textContent ?? "";
  const match =
    text.match(/\(?\s*([\d,]+)\s*(?:ratings?|reviews?)\s*\)?/i) ??
    text.match(/([\d,]+)\s+people rated/i);
  return truncate(match?.[0] ?? "", 32);
}

function extractAvailabilityText(element: HTMLElement): string {
  const text = element.textContent ?? "";
  const match = text.match(
    /in stock|out of stock|only \d+ left|unavailable|sold out|available/i,
  );
  return truncate(match?.[0] ?? "", 32);
}

function nearestLinkIndex(
  card: HTMLElement,
  ranked: ReturnType<typeof collectRankedInteractiveElements>,
): number | undefined {
  const link =
    card.querySelector<HTMLElement>("a[href]") ??
    (card.closest("a[href]") as HTMLElement | null);
  if (!link) {
    return undefined;
  }

  const position = ranked.findIndex((entry) => entry.element === link);
  return position >= 0 ? position + 1 : undefined;
}

function nearestAddToCartIndex(
  card: HTMLElement,
  ranked: ReturnType<typeof collectRankedInteractiveElements>,
): number | undefined {
  const button = card.querySelector<HTMLElement>(
    "button, [role='button'], input[type='submit']",
  );
  if (!button) {
    return undefined;
  }

  const label = (button.textContent ?? "").trim().toLowerCase();
  if (!label.includes("add to cart") && !label.includes("buy now")) {
    return undefined;
  }

  const position = ranked.findIndex((entry) => entry.element === button);
  return position >= 0 ? position + 1 : undefined;
}

function collectProductLikeItems(): PageProductSummary[] {
  const selectors = [
    "[data-component-type='s-search-result']",
    "[data-asin]",
    ".s-result-item",
    "[data-product]",
    "article",
    "[class*='product']",
    "[class*='Product']",
    "[class*='item-card']",
  ];

  const ranked = collectRankedInteractiveElements(MAX_PAGE_ELEMENTS);
  const products: PageProductSummary[] = [];
  const seen = new Set<string>();

  for (const selector of selectors) {
    for (const node of Array.from(document.querySelectorAll<HTMLElement>(selector))) {
      if (!isVisible(node) || isInsideOverlay(node)) {
        continue;
      }

      const className = node.className.toString();
      const text = node.textContent ?? "";
      const hasProductClass = PRODUCT_CLASS_HINT.test(className);
      const priceMatch = text.match(PRICE_HINT);

      if (!hasProductClass && !priceMatch && !node.hasAttribute("data-asin")) {
        continue;
      }

      const title = extractProductTitle(node);
      const priceText = truncate(priceMatch?.[0] ?? "");
      const ratingText = extractRatingText(node);
      const reviewCountText = extractReviewCountText(node);
      const availabilityText = extractAvailabilityText(node);
      const key = `${title}|${priceText}`;

      if (!title || title.length < 3 || seen.has(key)) {
        continue;
      }

      seen.add(key);
      products.push({
        title,
        priceText,
        ratingText: ratingText || undefined,
        reviewCountText: reviewCountText || undefined,
        availabilityText: availabilityText || undefined,
        elementIndex: nearestLinkIndex(node, ranked),
        addToCartElementIndex: nearestAddToCartIndex(node, ranked),
      });

      if (products.length >= MAX_PAGE_PRODUCTS) {
        return products;
      }
    }
  }

  return products;
}

export function extractPageContext(): PageContext {
  return {
    title: truncate(document.title || "Untitled page"),
    url: window.location.href,
    elements: collectInteractiveElements(),
    products: collectProductLikeItems(),
  };
}
