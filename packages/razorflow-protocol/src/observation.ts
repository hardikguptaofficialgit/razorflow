/**
 * Generic browser observation — no ecommerce-specific required fields.
 * Commerce hints (listings, cart) are optional environment extensions.
 */

export type ElementRole =
  | "search"
  | "input"
  | "button"
  | "link"
  | "select"
  | "textarea"
  | "checkbox"
  | "radio"
  | "tab"
  | "menu"
  | "dialog"
  | "unknown";

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface InteractiveElement {
  id: string;
  index: number;
  role: ElementRole;
  tag: string;
  text: string;
  ariaLabel: string;
  placeholder: string;
  href: string;
  value: string;
  visible: boolean;
  enabled: boolean;
  clickable: boolean;
  typeable: boolean;
  bbox?: BoundingBox;
  /** Semantic parent group id, e.g. form-1, card-3, dialog-1 */
  groupId?: string;
}

export interface SemanticGroup {
  id: string;
  kind: "form" | "card" | "dialog" | "navigation" | "list" | "region" | "custom";
  label: string;
  elementIds: string[];
}

export interface ListingHint {
  id: string;
  title: string;
  subtitle: string;
  actionElementId?: string;
  linkElementId?: string;
}

export interface CartHint {
  lines: Array<{ title: string; quantity: number; removeElementId?: string }>;
}

/** Optional environment-specific commerce data — NOT required by core runtime. */
export interface EnvironmentHints {
  listings?: ListingHint[];
  cart?: CartHint;
  custom?: Record<string, unknown>;
}

export interface BrowserObservation {
  url: string;
  title: string;
  path: string;
  viewport: { width: number; height: number };
  elements: InteractiveElement[];
  groups: SemanticGroup[];
  visibleTextSample: string;
  signals: string[];
  hints?: EnvironmentHints;
  screenshotDataUrl?: string;
  capturedAt: number;
}

/** Wire-compatible page context (superset used over WebSocket today). */
export interface PageContextWire {
  title: string;
  url: string;
  elements: Array<{
    index: number;
    role: string;
    tag: string;
    text: string;
    placeholder: string;
    ariaLabel: string;
    href?: string;
    value?: string;
    enabled?: boolean;
    bboxX?: number;
    bboxY?: number;
    bboxWidth?: number;
    bboxHeight?: number;
  }>;
  products?: Array<{
    title: string;
    priceText: string;
    ratingText?: string;
    reviewCountText?: string;
    availabilityText?: string;
    elementIndex?: number;
    addToCartElementIndex?: number;
  }>;
  cartLines?: Array<{
    title: string;
    quantity: number;
    removeElementIndex?: number;
  }>;
  screenshotDataUrl?: string;
}
