import { products } from "@/data/products";
import type { Product } from "@/data/types";
import { expandSearchToken } from "@/lib/search-query";

const CATEGORY_SYNONYMS: Record<string, string[]> = {
  fashion: [
    "dress",
    "dresses",
    "shirt",
    "tshirt",
    "t-shirt",
    "tee",
    "shoes",
    "sneakers",
    "party",
    "wear",
    "outfit",
    "clothing",
    "clothes",
  ],
  electronics: [
    "earbuds",
    "earbud",
    "buds",
    "tws",
    "headphones",
    "headphone",
    "headset",
    "watch",
    "smartwatch",
    "band",
    "trimmer",
    "gadget",
    "wireless",
    "bluetooth",
  ],
  "personal-care": [
    "shampoo",
    "soap",
    "beauty",
    "bar",
    "bars",
    "facewash",
    "face-wash",
    "gel",
    "skincare",
    "care",
  ],
  snacks: ["chips", "cookies", "chocolate", "chocolates", "butter", "snack"],
  home: ["bulb", "cooker", "dinner", "kitchen", "home"],
};

const SEARCH_STOPWORDS = new Set([
  "a",
  "an",
  "the",
  "and",
  "or",
  "to",
  "of",
  "for",
  "in",
  "on",
  "at",
  "with",
  "from",
  "by",
  "my",
  "me",
  "i",
  "you",
  "u",
  "your",
  "please",
  "hey",
  "hi",
  "hello",
  "can",
  "could",
  "help",
  "find",
  "search",
  "get",
  "buy",
  "want",
  "need",
  "some",
  "any",
  "good",
  "best",
  "nice",
  "great",
  "cheap",
  "cheapest",
  "add",
  "cart",
  "tonight",
  "today",
  "now",
  "under",
  "below",
  "above",
  "rs",
  "inr",
  "rupees",
]);

const MODIFIER_TOKENS = new Set([
  "wireless",
  "bluetooth",
  "portable",
  "rechargeable",
  "smart",
  "digital",
  "electric",
  "new",
  "latest",
  "premium",
  "affordable",
]);

function tokenize(query: string): string[] {
  return query
    .trim()
    .toLowerCase()
    .split(/[^a-z0-9+&-]+/)
    .filter((token) => token.length >= 2 && !SEARCH_STOPWORDS.has(token));
}

function productHaystack(product: Product): string {
  return `${product.name} ${product.category} ${product.description}`.toLowerCase();
}

function tokenMatchesHaystack(token: string, haystack: string): boolean {
  const forms = expandSearchToken(token);
  if (forms.some((form) => haystack.includes(form))) {
    return true;
  }

  for (const [category, synonyms] of Object.entries(CATEGORY_SYNONYMS)) {
    if (
      synonyms.some((synonym) => forms.includes(synonym)) &&
      haystack.includes(category)
    ) {
      return true;
    }
  }

  return false;
}

function scoreProduct(product: Product, tokens: string[]): number {
  const haystack = productHaystack(product);
  const primaryTokens = tokens.filter((token) => !MODIFIER_TOKENS.has(token));
  const requiredTokens = primaryTokens.length > 0 ? primaryTokens : tokens;

  let score = 0;
  let primaryHits = 0;

  for (const token of tokens) {
    const forms = expandSearchToken(token);
    const name = product.name.toLowerCase();

    for (const form of forms) {
      if (name.includes(form)) {
        score += 14;
      } else if (haystack.includes(form)) {
        score += 5;
      }
    }

    for (const [category, synonyms] of Object.entries(CATEGORY_SYNONYMS)) {
      if (
        product.category === category &&
        synonyms.some((synonym) => forms.includes(synonym))
      ) {
        score += 4;
      }
    }
  }

  for (const token of requiredTokens) {
    if (tokenMatchesHaystack(token, haystack)) {
      primaryHits += 1;
    }
  }

  if (requiredTokens.length > 0 && primaryHits === 0) {
    return 0;
  }

  if (primaryTokens.length > 1 && primaryHits < Math.min(2, primaryTokens.length)) {
    score = Math.floor(score * 0.55);
  }

  return score;
}

export function getProducts(): Product[] {
  return [...products];
}

export function getProductById(id: string): Product | undefined {
  return products.find((product) => product.id === id);
}

export function searchProducts(query: string): Product[] {
  const tokens = tokenize(query);
  if (tokens.length === 0) {
    return getProducts();
  }

  const scored = products
    .map((product) => ({
      product,
      score: scoreProduct(product, tokens),
    }))
    .filter((entry) => entry.score > 0)
    .sort((left, right) => right.score - left.score);

  if (scored.length === 0) {
    return [];
  }

  return scored.map((entry) => entry.product);
}
