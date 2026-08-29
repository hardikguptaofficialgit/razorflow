/** Conversational goals → short store search queries (aligned with agent-backend). */

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
  "im",
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
  "budget",
  "under",
  "below",
  "above",
  "rs",
  "inr",
  "add",
  "cart",
  "checkout",
  "rating",
  "ratings",
  "rated",
  "stars",
  "reviews",
  "product",
  "products",
  "price",
  "prices",
]);

const MODIFIER_WORDS = new Set([
  "wireless",
  "bluetooth",
  "portable",
  "rechargeable",
  "smart",
  "digital",
  "electric",
  "online",
  "new",
  "latest",
  "premium",
  "affordable",
]);

const PRODUCT_TERMS = new Set([
  "shampoo",
  "chocolate",
  "chocolates",
  "chips",
  "cookies",
  "dress",
  "dresses",
  "shoes",
  "sneakers",
  "headphones",
  "headphone",
  "earbuds",
  "earbud",
  "buds",
  "watch",
  "watches",
  "smartwatch",
  "beauty",
  "bar",
  "bars",
  "trimmer",
  "facewash",
  "cooker",
  "bulb",
  "butter",
  "bag",
  "bags",
  "luggage",
  "backpack",
  "handbag",
  "gucci",
  "nike",
  "adidas",
  "puma",
  "boat",
  "noise",
]);

const CANONICAL_FORMS: Record<string, string> = {
  earbud: "earbuds",
  earbuds: "earbuds",
  headphone: "headphones",
  headphones: "headphones",
  chocolate: "chocolates",
  chocolates: "chocolates",
  dress: "dresses",
  bag: "bags",
  watch: "smartwatch",
  watches: "smartwatch",
};

const TERM_SYNONYMS: Record<string, string[]> = {
  earbud: ["earbud", "earbuds", "buds", "tws"],
  earbuds: ["earbud", "earbuds", "buds", "tws"],
  buds: ["buds", "earbuds", "earbud"],
  headphone: ["headphone", "headphones", "headset", "rockerz"],
  headphones: ["headphone", "headphones", "headset", "rockerz"],
  watch: ["watch", "watches", "smartwatch"],
  watches: ["watch", "watches", "smartwatch"],
  smartwatch: ["watch", "watches", "smartwatch"],
  beauty: ["beauty", "moisturizing", "dove", "bar", "bars"],
  bar: ["bar", "bars", "beauty"],
  bars: ["bar", "bars", "beauty"],
  chocolates: ["chocolate", "chocolates", "cadbury", "ferrero"],
  chocolate: ["chocolate", "chocolates", "cadbury", "ferrero"],
};

function canonicalize(token: string): string {
  return CANONICAL_FORMS[token] ?? token;
}

function isProductTerm(token: string): boolean {
  return (
    PRODUCT_TERMS.has(token) ||
    PRODUCT_TERMS.has(token.replace(/s$/, "")) ||
    PRODUCT_TERMS.has(`${token}s`)
  );
}

function stripBudgetFragments(text: string): string {
  return text
    .replace(
      /\b(?:under|below|less than|upto|up to|max(?:imum)?)\s*(?:₹|rs\.?|inr|\$|usd)?\s*[\d,]+(?:\.\d+)?\s*k\b/gi,
      " ",
    )
    .replace(
      /\b(?:under|below|less than|upto|up to|max(?:imum)?)\s*(?:₹|rs\.?|inr|\$|usd)?\s*[\d,]+(?:\.\d+)?\b/gi,
      " ",
    )
    .replace(/\b[\d,]+(?:\.\d+)?\s*k\b/gi, " ")
    .replace(/\b(?:₹|rs\.?|inr|\$|usd)\s*[\d,]+(?:\.\d+)?\b/gi, " ");
}

/** Turn a chatty goal or noisy type text into a short catalog search query. */
export function extractSearchQuery(task: string): string {
  let text = task.trim().toLowerCase();
  text = text.replace(/[^\w\s\-+&]/g, " ");
  text = stripBudgetFragments(text);
  text = text
    .replace(/\b(add\s+to\s+(cart|bag|basket)|buy\s+now|check\s*out)\b.*$/i, " ")
    .replace(/\s+/g, " ")
    .trim();

  const tokens = text
    .split(" ")
    .filter(
      (token) =>
        token.length > 1 &&
        !SEARCH_STOPWORDS.has(token) &&
        !["ok", "go", "um", "uh"].includes(token),
    );

  const productTokens = tokens.filter(isProductTerm);
  const chosen =
    productTokens.length > 0
      ? productTokens.filter((token) => !MODIFIER_WORDS.has(token))
      : tokens.filter((token) => !MODIFIER_WORDS.has(token));

  const pool = (chosen.length > 0 ? chosen : tokens).slice(0, 4);
  const brands = pool.filter((token) =>
    ["gucci", "nike", "adidas", "puma", "boat", "noise"].includes(token),
  );
  const nouns = pool.filter((token) => !brands.includes(token));
  const ordered = [...brands, ...nouns].map(canonicalize);

  const query = [...new Set(ordered)].join(" ").trim();
  return query || tokens.slice(0, 3).join(" ") || task.trim().slice(0, 40);
}

/** Strip budget noise from LLM-typed search text. */
export function sanitizeSearchQuery(text: string): string {
  const stripped = stripBudgetFragments(text).replace(/\s+/g, " ").trim();
  if (!stripped) {
    return "";
  }
  return extractSearchQuery(stripped) || stripped;
}

export function expandSearchToken(token: string): string[] {
  const forms = new Set<string>([token, canonicalize(token)]);
  const synonyms = TERM_SYNONYMS[token] ?? TERM_SYNONYMS[token.replace(/s$/, "")];
  if (synonyms) {
    for (const synonym of synonyms) {
      forms.add(synonym);
    }
  }
  return [...forms];
}

export function searchQueriesEquivalent(a: string, b: string): boolean {
  const left = sanitizeSearchQuery(a).toLowerCase();
  const right = sanitizeSearchQuery(b).toLowerCase();
  if (!left || !right) {
    return false;
  }
  if (left === right) {
    return true;
  }

  const tokensA = new Set(left.split(" ").filter(Boolean));
  const tokensB = new Set(right.split(" ").filter(Boolean));
  if (tokensA.size === tokensB.size && [...tokensA].every((token) => tokensB.has(token))) {
    return true;
  }

  const expandedA = new Set(
    [...tokensA].flatMap((token) => expandSearchToken(token)),
  );
  const expandedB = new Set(
    [...tokensB].flatMap((token) => expandSearchToken(token)),
  );

  const primaryA = [...tokensA].filter((token) => !MODIFIER_WORDS.has(token));
  const primaryB = [...tokensB].filter((token) => !MODIFIER_WORDS.has(token));
  const primariesA = primaryA.length > 0 ? primaryA : [...tokensA];
  const primariesB = primaryB.length > 0 ? primaryB : [...tokensB];

  return primariesA.some((token) =>
    expandSearchToken(token).some((form) => expandedB.has(form)),
  ) && primariesB.some((token) =>
    expandSearchToken(token).some((form) => expandedA.has(form)),
  );
}
