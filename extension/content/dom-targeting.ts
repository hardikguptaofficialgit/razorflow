import type {
  DomTargetMatch,
  ElementMetadata,
  HighlightRect,
  CursorPosition,
  TargetRole,
} from "../shared/types";
import { OVERLAY_ROOT_ID } from "../shared/types";

const SEARCH_HINT = /search|query|find|keyword/i;
const BUTTON_HINT = /search|submit|go|find|buy|add|cart|checkout/i;

export interface RankedInteractiveElement {
  element: HTMLElement;
  role: TargetRole;
  metadata: ElementMetadata;
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
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

function isEnabled(element: HTMLElement): boolean {
  if (element.hasAttribute("disabled") || element.getAttribute("aria-disabled") === "true") {
    return false;
  }

  if (element instanceof HTMLInputElement && element.disabled) {
    return false;
  }

  if (element instanceof HTMLButtonElement && element.disabled) {
    return false;
  }

  if (element instanceof HTMLAnchorElement && !element.href) {
    return false;
  }

  return true;
}

function isPasswordField(element: Element): boolean {
  if (!(element instanceof HTMLInputElement)) {
    return false;
  }

  if (element.type === "password") {
    return true;
  }

  const autocomplete = element.autocomplete.toLowerCase();
  if (autocomplete.includes("password")) {
    return true;
  }

  const identity = `${element.name} ${element.id}`.toLowerCase();
  return identity.includes("password");
}

function isTextEntryElement(
  element: Element,
): element is HTMLInputElement | HTMLTextAreaElement {
  if (element instanceof HTMLTextAreaElement) {
    return true;
  }

  if (!(element instanceof HTMLInputElement)) {
    return false;
  }

  if (isPasswordField(element)) {
    return false;
  }

  return ["text", "search", "email", "tel", "url", "number"].includes(
    element.type,
  );
}

function getHintText(element: HTMLElement): string {
  const parts = [
    element.getAttribute("name") ?? "",
    element.id,
    element.getAttribute("aria-label") ?? "",
    element.getAttribute("placeholder") ?? "",
    element.textContent ?? "",
  ];

  return parts.join(" ").trim();
}

function looksLikeSearchField(element: HTMLElement): boolean {
  if (element instanceof HTMLInputElement && element.type === "search") {
    return true;
  }

  if (element.getAttribute("role") === "searchbox") {
    return true;
  }

  return SEARCH_HINT.test(getHintText(element));
}

function looksLikeActionButton(element: HTMLElement): boolean {
  return BUTTON_HINT.test(getHintText(element));
}

function inferRole(element: HTMLElement): TargetRole | null {
  if (element instanceof HTMLAnchorElement && element.href) {
    return "link";
  }

  if (
    element instanceof HTMLButtonElement ||
    element.getAttribute("role") === "button" ||
    (element instanceof HTMLInputElement &&
      ["button", "submit"].includes(element.type))
  ) {
    return "button";
  }

  if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
    if (element.type === "search" || element.getAttribute("role") === "searchbox") {
      return "search";
    }

    if (looksLikeSearchField(element)) {
      return "search";
    }

    return "input";
  }

  return null;
}

export function getElementMetadata(element: HTMLElement): ElementMetadata {
  return {
    tag: element.tagName.toLowerCase(),
    text: (element.textContent ?? "").trim().slice(0, 80),
    placeholder:
      element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement
        ? element.placeholder
        : "",
    ariaLabel: element.getAttribute("aria-label") ?? "",
  };
}

export function getElementGeometry(element: HTMLElement): {
  rect: HighlightRect;
  center: CursorPosition;
} {
  const bounds = element.getBoundingClientRect();

  return {
    rect: {
      x: bounds.x,
      y: bounds.y,
      width: bounds.width,
      height: bounds.height,
    },
    center: {
      x: bounds.x + bounds.width / 2,
      y: bounds.y + bounds.height / 2,
    },
  };
}

export function refreshTargetMatch(match: DomTargetMatch): DomTargetMatch {
  const geometry = getElementGeometry(match.element);

  return {
    ...match,
    metadata: getElementMetadata(match.element),
    rect: geometry.rect,
    center: geometry.center,
  };
}

/** Visible, enabled, and large enough to receive a real click. */
export function isElementActionable(element: HTMLElement): boolean {
  if (!element.isConnected) {
    return false;
  }
  if (!isVisible(element) || !isEnabled(element)) {
    return false;
  }
  const rect = element.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) {
    return false;
  }
  // Must intersect the viewport (after scrollIntoView callers settle).
  if (
    rect.bottom < 0 ||
    rect.top > window.innerHeight ||
    rect.right < 0 ||
    rect.left > window.innerWidth
  ) {
    return false;
  }
  return true;
}

function elementMatchesRole(element: HTMLElement, role: TargetRole): boolean {
  const inferred = inferRole(element);
  if (inferred === role) {
    return true;
  }
  // Search fields are also typeable as input; product links may be buttons.
  if (role === "input" && (inferred === "search" || isTextEntryElement(element))) {
    return true;
  }
  if (role === "button" && inferred === "link") {
    return true;
  }
  return false;
}

function elementMatchesText(element: HTMLElement, matchText: string): boolean {
  const needle = matchText.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  const haystack = [
    getElementMetadata(element).text,
    getElementMetadata(element).placeholder,
    getElementMetadata(element).ariaLabel,
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(needle) || needle.includes(haystack.slice(0, 24));
}

function toTargetMatch(element: HTMLElement): DomTargetMatch {
  const geometry = getElementGeometry(element);

  return {
    element,
    metadata: getElementMetadata(element),
    rect: geometry.rect,
    center: geometry.center,
  };
}

function scoreCandidate(element: HTMLElement, role: TargetRole): number {
  const rect = element.getBoundingClientRect();
  let score = 0;

  if (rect.top >= 0 && rect.top < window.innerHeight) {
    score += 40;
  }

  if (rect.left >= 0 && rect.left < window.innerWidth) {
    score += 20;
  }

  if (role === "search" || looksLikeSearchField(element)) {
    score += 80;
  }

  if (role === "button" && looksLikeActionButton(element)) {
    score += 60;
  }

  score += Math.max(0, 30 - rect.top / 40);

  return score;
}

function collectCandidates(selector: string): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>(selector)).filter(
    (element) => isVisible(element) && isEnabled(element) && !isPasswordField(element),
  );
}

function pickBest(candidates: HTMLElement[], role?: TargetRole): DomTargetMatch | null {
  if (candidates.length === 0) {
    return null;
  }

  const ranked = [...candidates].sort((left, right) => {
    const leftRole = inferRole(left) ?? role ?? "button";
    const rightRole = inferRole(right) ?? role ?? "button";
    return scoreCandidate(right, rightRole) - scoreCandidate(left, leftRole);
  });

  return toTargetMatch(ranked[0]);
}

export function collectRankedInteractiveElements(
  maxElements = 25,
): RankedInteractiveElement[] {
  const selectors = [
    'input:not([type="hidden"]):not([type="password"])',
    "textarea",
    "button",
    "a[href]",
    "[role='button']",
    "[role='searchbox']",
  ];

  const seen = new Set<HTMLElement>();
  const candidates: RankedInteractiveElement[] = [];

  for (const selector of selectors) {
    for (const node of collectCandidates(selector)) {
      if (seen.has(node)) {
        continue;
      }

      const role = inferRole(node);
      if (!role) {
        continue;
      }

      seen.add(node);
      candidates.push({
        element: node,
        role,
        metadata: getElementMetadata(node),
      });
    }
  }

  return candidates
    .sort(
      (left, right) =>
        scoreCandidate(right.element, right.role) -
        scoreCandidate(left.element, left.role),
    )
    .slice(0, maxElements);
}

export function findByElementIndex(elementIndex: number): DomTargetMatch | null {
  if (!Number.isInteger(elementIndex) || elementIndex < 1) {
    return null;
  }

  const ranked = collectRankedInteractiveElements();
  const entry = ranked[elementIndex - 1];
  if (!entry) {
    return null;
  }

  return toTargetMatch(entry.element);
}

export function findSearchField(): DomTargetMatch | null {
  const searchSelectors = [
    'input[type="search"]',
    '[role="searchbox"]',
    'input[name*="search" i]',
    'input[id*="search" i]',
    'input[placeholder*="search" i]',
    'textarea[name*="search" i]',
    'textarea[placeholder*="search" i]',
  ];

  for (const selector of searchSelectors) {
    const match = pickBest(collectCandidates(selector), "search");
    if (match) {
      return match;
    }
  }

  const textInputs = collectCandidates(
    'input[type="text"], input:not([type]), textarea',
  ).filter(isTextEntryElement);

  const searchLike = textInputs.filter((element) => looksLikeSearchField(element));
  return pickBest(searchLike.length > 0 ? searchLike : textInputs, "search");
}

export function findInputField(): DomTargetMatch | null {
  const candidates = collectCandidates(
    'input[type="text"], input[type="search"], input[type="email"], input[type="tel"], input[type="url"], input[type="number"], input:not([type]), textarea',
  ).filter(isTextEntryElement);

  return pickBest(candidates, "input");
}

export function findButtonElement(): DomTargetMatch | null {
  const candidates = collectCandidates(
    "button, input[type='submit'], input[type='button'], [role='button']",
  );

  const actionButtons = candidates.filter((element) =>
    looksLikeActionButton(element),
  );

  return pickBest(actionButtons.length > 0 ? actionButtons : candidates, "button");
}

export function findLinkElement(): DomTargetMatch | null {
  return pickBest(collectCandidates("a[href]"), "link");
}

export function findByMatchText(
  role: TargetRole | undefined,
  matchText: string,
): DomTargetMatch | null {
  const needle = matchText.trim().toLowerCase();
  if (!needle) {
    return null;
  }

  const ranked = collectRankedInteractiveElements();
  let best: { entry: (typeof ranked)[number]; score: number } | null = null;

  for (const entry of ranked) {
    if (role && entry.role !== role) {
      continue;
    }

    const haystack = [
      entry.metadata.text,
      entry.metadata.placeholder,
      entry.metadata.ariaLabel,
    ]
      .join(" ")
      .toLowerCase();

    if (!haystack) {
      continue;
    }

    let score = 0;
    if (haystack === needle) {
      score = 100;
    } else if (haystack.includes(needle)) {
      score = 70;
    } else if (needle.includes(haystack.slice(0, 24)) && haystack.length > 3) {
      score = 40;
    } else {
      continue;
    }

    if (!best || score > best.score) {
      best = { entry, score };
    }
  }

  return best ? toTargetMatch(best.entry.element) : null;
}

export function findByRole(
  role: TargetRole,
  elementIndex?: number,
  matchText?: string,
): DomTargetMatch | null {
  if (elementIndex !== undefined) {
    const indexed = findByElementIndex(elementIndex);
    if (indexed) {
      const okRole = elementMatchesRole(indexed.element, role);
      const okText =
        !matchText?.trim() || elementMatchesText(indexed.element, matchText);
      // Only trust elementIndex when it agrees with role (and matchText if given).
      if (okRole && okText && isElementActionable(indexed.element)) {
        return indexed;
      }
      // Index stale or mismatched — fall through to role/text rediscovery.
    }
  }

  if (matchText?.trim()) {
    const matched = findByMatchText(role, matchText);
    if (matched && isElementActionable(matched.element)) {
      return matched;
    }
  }

  let fallback: DomTargetMatch | null = null;
  switch (role) {
    case "search":
      fallback = findSearchField();
      break;
    case "input":
      fallback = findInputField();
      break;
    case "button":
      fallback = findButtonElement();
      break;
    case "link":
      fallback = findLinkElement();
      break;
  }

  if (fallback && isElementActionable(fallback.element)) {
    return fallback;
  }
  return null;
}

export function findSearchOrInput(): DomTargetMatch | null {
  return findSearchField() ?? findInputField();
}
