import type { TargetRole } from "./types";

export const MAX_PAGE_ELEMENTS = 40;
export const MAX_PAGE_PRODUCTS = 8;
export const MAX_SUMMARY_TEXT_LENGTH = 80;

export interface PageElementSummary {
  index?: number;
  role: TargetRole;
  tag: string;
  text: string;
  placeholder: string;
  ariaLabel: string;
}

export interface PageProductSummary {
  title: string;
  priceText: string;
  ratingText?: string;
  reviewCountText?: string;
  availabilityText?: string;
  elementIndex?: number;
  addToCartElementIndex?: number;
}

export interface PageContext {
  title: string;
  url: string;
  elements: PageElementSummary[];
  products: PageProductSummary[];
}

export interface GetPageContextRequest {
  type: "GET_PAGE_CONTEXT";
}

export interface GetPageContextResponse {
  pageContext: PageContext;
}

export function isGetPageContextRequest(
  message: unknown,
): message is GetPageContextRequest {
  return (
    typeof message === "object" &&
    message !== null &&
    (message as { type?: string }).type === "GET_PAGE_CONTEXT"
  );
}
