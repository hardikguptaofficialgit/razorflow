# Core vs Domain Audit: Hardcoded Dependencies in RazorFlow

## Purpose

This document maps every hardcoded dependency in RazorFlow's core agent logic to separate:
- **A. Generic browser capabilities** (keep in core)
- **B. Shopping-specific intelligence** (move to optional domain skills)
- **C. Fake-store-specific behavior** (remove or make optional)

## Files Audited

1. `agent-backend/core/plan_guard_store.py` (564 lines)
2. `agent-backend/core/store_planner.py` (97 lines)
3. `agent-backend/core/task_interpretation.py` (88 lines)
4. `agent-backend/core/search_query.py` (506 lines)
5. `agent-backend/core/shopping_intent.py` (264 lines)
6. `agent-backend/core/heuristics.py` (609 lines)

---

## 1. plan_guard_store.py (564 lines)

### Overview
Applies store-specific DOM guards to override LLM decisions. Only activates for RazorFlow URLs.

### Hardcoded Dependencies

#### C. Fake-store-specific behavior

**Line 24-34: Store category labels**
```python
_STORE_CATEGORY_LABELS = frozenset(
    {
        "all",
        "electronics",
        "personal care",
        "snacks",
        "home",
        "fashion",
    }
)
```
- **Type**: C (Fake-store-specific)
- **Used by**: `_filter_category_nav_steps()`, `_is_category_nav_step()`
- **Purpose**: Filter out category navigation clicks specific to fake-store
- **Impact**: Blocks legitimate category navigation on other sites

**Line 37-62: is_razorflow_store_url()**
```python
def is_razorflow_store_url(url: str) -> bool:
    if not url.strip():
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1"}:
        return True
    return "razorflow" in host
```
- **Type**: C (Fake-store-specific)
- **Used by**: `apply_store_dom_guard()` (entire file gated)
- **Purpose**: Guard all logic to only activate on RazorFlow URLs
- **Impact**: All shopping intelligence disabled on arbitrary sites

**Line 126-140: page_requires_login()**
```python
def page_requires_login(page) -> bool:
    url = (page.url or "").lower()
    title = (page.title or "").lower()
    blob = f"{url} {title}"
    if "auth=login" in url or "/login" in url:
        return True
    if "sign in to checkout" in blob or "sign in to continue" in blob:
        return True
    if page.elements and any(
        getattr(el, "tag", "") == "data-rf-auth-required" for el in page.elements
    ):
        return True
    if re.search(r"sign[\s-]?in|log[\s-]?in", blob):
        return bool(re.search(r"checkout|account|order", blob))
    return False
```
- **Type**: C (Fake-store-specific with some generic patterns)
- **Used by**: Multiple guard functions
- **Purpose**: Detect login pages for handoff
- **Impact**: `data-rf-auth-required` is fake-store custom attribute

**Line 192-198: _navigate_search()**
```python
def _navigate_search(page, query: str) -> PlannerChunkOutput:
    origin = _store_origin(page.url)
    search_url = f"{origin}/search?q={quote(query)}"
    return PlannerChunkOutput(
        steps=[NavigateUrlStep(action="navigate_url", url=search_url)],
        terminal="continue",
    )
```
- **Type**: C (Fake-store-specific URL pattern)
- **Used by**: Multiple guard functions
- **Purpose**: Force navigation to /search?q= pattern
- **Impact**: Won't work on sites with different search URL patterns

**Line 201-206: _navigate_checkout()**
```python
def _navigate_checkout(page) -> PlannerChunkOutput:
    origin = _store_origin(page.url)
    return PlannerChunkOutput(
        steps=[NavigateUrlStep(action="navigate_url", url=f"{origin}/checkout")],
        terminal="continue",
    )
```
- **Type**: C (Fake-store-specific URL pattern)
- **Used by**: `_should_proceed_to_checkout()`
- **Purpose**: Force navigation to /checkout
- **Impact**: Won't work on sites with different checkout patterns

**Line 38-42: _SHOP_HINT regex**
```python
_SHOP_HINT = re.compile(
    r"\b(buy|find|search|cheapest|cheap|lowest|price|cart|order|shop|purchase|"
    r"checkout|cooker|product|add to cart|rating|dress|snacks|earbuds?|wireless|home|watch)\b",
    re.I,
)
```
- **Type**: B (Shopping-specific)
- **Used by**: `apply_store_dom_guard()` gating
- **Purpose**: Detect shopping tasks to enable guards
- **Impact**: Guards disabled for non-shopping tasks even on RazorFlow URLs

#### B. Shopping-specific intelligence

**Line 209-242: _should_proceed_to_checkout()**
```python
def _should_proceed_to_checkout(
    session: RunSession,
    task_intent,
    page,
    path: str,
    has_cart_items: bool,
) -> bool:
    if not goal_allows_checkout(task_intent.goal):
        return False
    url = (page.url or "").lower()
    if path.startswith("/checkout"):
        return False
    if "auth=login" in url and "next=/checkout" in url.replace("%2f", "/"):
        return False

    adds = count_successful_adds(session)
    needs_add = bool(
        re.search(r"\badd\b", task_intent.raw_task, re.I)
        or len(task_intent.product_queries) >= 2
        or task_intent.add_target_count > 1
    )
    if needs_add and adds < task_intent.add_target_count and not has_cart_items:
        return False
    if not needs_add and not has_cart_items:
        return False

    if (
        adds < task_intent.add_target_count
        and path.startswith("/search")
        and page.products
        and goal_allows_add_to_cart(task_intent.goal)
    ):
        return False
    return True
```
- **Type**: B (Shopping-specific workflow logic)
- **Used by**: Main guard function
- **Purpose**: Decide when to proceed to checkout based on cart state
- **Impact**: Hardcoded checkout workflow logic

**Line 251-318: _pick_best_add_to_cart()**
```python
def _pick_best_add_to_cart(
    session: RunSession,
    page,
    intent,
    task_intent,
) -> PlannerChunkOutput:
    if not goal_allows_add_to_cart(task_intent.goal):
        if is_goal_satisfied(session, task_intent, page):
            return complete_chunk()
        return PlannerChunkOutput(
            steps=[WaitForUserStep(action="wait_for_user")],
            terminal="wait_for_user",
        )

    if count_successful_adds(session) >= task_intent.add_target_count:
        logger.info(
            "Store guard: add goal satisfied runId=%s adds=%s target=%s",
            session.run_id,
            count_successful_adds(session),
            task_intent.add_target_count,
        )
        return complete_chunk()

    best, _candidates, reason = select_best_product(
        page,
        intent,
        exclude_element_indices=used_add_element_indices(session),
    )
    # ... product selection logic
```
- **Type**: B (Shopping-specific product selection)
- **Used by**: Multiple guard functions
- **Purpose**: Override LLM to pick best product based on constraints
- **Impact**: Hardcoded shopping decision logic

**Line 147-162: _is_add_to_cart_step(), _is_cart_nav_step(), _is_checkout_step()**
```python
def _is_add_to_cart_step(step) -> bool:
    if not isinstance(step, ClickElementStep):
        return False
    label = (step.match_text or "").strip().lower()
    return "add to cart" in label or "buy now" in label

def _is_cart_nav_step(step) -> bool:
    if not isinstance(step, ClickElementStep):
        return False
    if _is_add_to_cart_step(step):
        return False
    label = (step.match_text or "").lower().strip()
    if label in {"cart", "go to cart", "view cart", "bag", "basket"}:
        return True
    return "cart" in label and "add" not in label

def _is_checkout_step(step) -> bool:
    if not isinstance(step, ClickElementStep):
        return False
    label = (step.match_text or "").lower()
    return bool(
        re.search(
            r"proceed to checkout|proceed to buy|checkout|place order|pay now",
            label,
        )
    )
```
- **Type**: B (Shopping-specific action classification)
- **Used by**: `_block_beyond_goal()`, goal filtering
- **Purpose**: Detect shopping-specific actions
- **Impact**: Hardcoded action labels may not match other sites

#### A. Generic browser capabilities

**Line 330-387: _block_beyond_goal()**
```python
def _block_beyond_goal(
    session: RunSession,
    chunk: PlannerChunkOutput,
    task_intent,
    page,
    intent,
    path: str,
    has_cart_items: bool,
) -> PlannerChunkOutput | None:
    if is_goal_satisfied(session, task_intent, page):
        return complete_chunk()

    filtered_steps = filter_steps_for_goal(chunk.steps, task_intent)
    # ... goal-based filtering logic
```
- **Type**: A (Generic goal enforcement - but uses shopping-specific filters)
- **Used by**: Main guard function
- **Purpose**: Prevent actions beyond task scope
- **Impact**: Currently tightly coupled to shopping goals

**Line 67-78: _searched_queries()**
```python
def _searched_queries(session: RunSession) -> set[str]:
    queries: set[str] = set()
    for entry in session.history:
        if not entry.success:
            continue
        step = entry.step
        if getattr(step, "action", "") != "navigate_url":
            continue
        url_query = _url_search_query(getattr(step, "url", ""))
        if url_query:
            queries.add(url_query.lower())
    return queries
```
- **Type**: A (Generic query tracking)
- **Used by**: Empty search handling
- **Purpose**: Track what has been searched for
- **Impact**: Generic capability, but used in shopping context

### Summary

- **C (Fake-store-specific)**: ~200 lines (URL patterns, category labels, custom attributes)
- **B (Shopping-specific)**: ~250 lines (workflow logic, action classification, product selection)
- **A (Generic)**: ~114 lines (goal enforcement, query tracking - but shopping-coupled)

### Refactor Plan

1. Extract `_searched_queries()` to generic utilities
2. Make goal enforcement generic (decouple from shopping-specific filters)
3. Move shopping workflow logic to optional domain skill
4. Remove URL pattern assumptions
5. Remove fake-store custom attribute checks
6. Make action classification pattern-based, not hardcoded

---

## 2. store_planner.py (97 lines)

### Overview
Deterministic fast-path planner that skips LLM for obvious RazorFlow Market actions.

### Hardcoded Dependencies

#### C. Fake-store-specific behavior

**Line 17-21: _SHOP_HINT regex**
```python
_SHOP_HINT = re.compile(
    r"\b(buy|find|search|cheapest|cheap|lowest|price|cart|order|shop|purchase|"
    r"checkout|shampoo|product|add to cart|rating|dress|snacks|earbuds)\b",
    re.I,
)
```
- **Type**: B (Shopping-specific)
- **Used by**: `try_store_fast_plan()` gating
- **Purpose**: Detect shopping tasks
- **Impact**: Fast-path disabled for non-shopping

**Line 24-34: is_razorflow_store_url()**
```python
def is_razorflow_store_url(url: str) -> bool:
    if not url.strip():
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1"}:
        return True
    return "razorflow" in host
```
- **Type**: C (Fake-store-specific)
- **Used by**: `try_store_fast_plan()` gating
- **Purpose**: Only activate on RazorFlow URLs
- **Impact**: Fast-path disabled on other sites

**Line 87-96: Search URL construction**
```python
origin = _store_origin(page.url)
search_url = f"{origin}/search?q={quote(query)}"
logger.info(
    "Store fast path: navigate search runId=%s query=%s",
    session.run_id,
    query,
)
return PlannerChunkOutput(
    steps=[NavigateUrlStep(action="navigate_url", url=search_url)],
    terminal="continue",
)
```
- **Type**: C (Fake-store-specific URL pattern)
- **Used by**: `try_store_fast_plan()`
- **Purpose**: Force /search?q= navigation
- **Impact**: Won't work on other sites

#### B. Shopping-specific intelligence

**Line 42-96: try_store_fast_plan()**
```python
def try_store_fast_plan(session: RunSession) -> PlannerChunkOutput | None:
    """Skip LLM when we can jump straight to a known store route."""
    page = session.latest_page_context
    if page is None or not is_razorflow_store_url(page.url):
        return None
    task_intent = parse_task_intent(session.task)
    if task_intent.goal in {"view_cart", "remove", "update_cart"}:
        return None

    if not _SHOP_HINT.search(session.task):
        return None

    query = get_active_product_query(task_intent, session) or extract_search_query(session.task)
    if not query:
        return None

    # ... URL pattern checks and search navigation
```
- **Type**: B (Shopping-specific fast-path logic)
- **Used by**: `agent_loop.py` `_store_plan()`
- **Purpose**: Skip LLM for obvious shopping actions
- **Impact**: Hardcoded shopping workflow assumptions

#### A. Generic browser capabilities

**Line 37-39: _store_origin()**
```python
def _store_origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"
```
- **Type**: A (Generic URL utility)
- **Used by**: Search/checkout URL construction
- **Purpose**: Extract origin for URL construction
- **Impact**: Generic, but used for hardcoded patterns

### Summary

- **C (Fake-store-specific)**: ~30 lines (URL gating, URL patterns)
- **B (Shopping-specific)**: ~50 lines (shopping workflow fast-path)
- **A (Generic)**: ~3 lines (URL utility)

### Refactor Plan

1. Extract `_store_origin()` to generic URL utilities
2. Make fast-path optional and pattern-based (not URL-gated)
3. Remove hardcoded /search?q= pattern
4. Move shopping fast-path to optional domain skill
5. Allow generic URL heuristics for any site

---

## 3. task_interpretation.py (88 lines)

### Overview
Parses user task to determine if it's actionable and extracts shopping goal.

### Hardcoded Dependencies

#### B. Shopping-specific intelligence

**Line 14-21: _SHOP_VERB_RE**
```python
_SHOP_VERB_RE = re.compile(
    r"\b("
    r"search|find|look\s+for|show\s+me|browse|buy|purchase|order|shop|"
    r"add|put|place|cart|checkout|check\s*out|remove|delete|view|open|see|"
    r"compare|get|grab|pick\s+up|earbuds?|snacks?|shampoo|product|checkout"
    r")\b",
    re.I,
)
```
- **Type**: B (Shopping-specific verb detection)
- **Used by**: `interpret_task()` gating
- **Purpose**: Reject non-shopping tasks
- **Impact**: Cannot handle arbitrary browser tasks

**Line 49-88: interpret_task()**
```python
def interpret_task(task: str) -> TaskInterpretation:
    raw = task.strip()
    intent = parse_task_intent(raw)

    if not raw:
        return TaskInterpretation(
            intent=intent,
            status="needs_clarification",
            reason="Please describe what you want to search, add, or buy.",
        )

    if _looks_gibberish(raw):
        return TaskInterpretation(
            intent=intent,
            status="needs_clarification",
            reason=(
                "I could not understand that request. Try something like "
                "'search for wireless earbuds' or 'add snacks under ₹200'."
            ),
        )

    if not _SHOP_VERB_RE.search(raw):
        return TaskInterpretation(
            intent=intent,
            status="needs_clarification",
            reason=(
                "That does not look like a shopping task. "
                "Ask me to search, add to cart, view cart, or checkout."
            ),
        )

    query = extract_search_query(raw)
    if intent.goal in {"search", "add_to_cart", "compare"} and len(query) < 2:
        return TaskInterpretation(
            intent=intent,
            status="needs_clarification",
            reason="Please name a product or category to search for.",
        )

    return TaskInterpretation(intent=intent, status="actionable")
```
- **Type**: B (Shopping-specific task validation)
- **Used by**: `agent_loop.py` `plan_next_action()`
- **Purpose**: Validate task is shopping-related
- **Impact**: Hardcoded shopping task assumptions

**Line 36-46: _looks_gibberish()**
```python
def _looks_gibberish(task: str) -> bool:
    cleaned = re.sub(r"\s+", "", task.strip().lower())
    if len(cleaned) < 2:
        return True
    if _GIBBERISH_RE.match(cleaned):
        return True
    if len(set(cleaned)) == 1 and len(cleaned) >= 3:
        return True
    if len(cleaned) <= 4 and not _SHOP_VERB_RE.search(task):
        return True
    return True
```
- **Type**: B (Shopping-specific gibberish detection)
- **Used by**: `interpret_task()`
- **Purpose**: Detect invalid tasks
- **Impact**: Uses shopping verbs for validation

#### A. Generic browser capabilities

**Line 22: _GIBBERISH_RE**
```python
_GIBBERISH_RE = re.compile(r"^[^a-zA-Z0-9]*$")
```
- **Type**: A (Generic input validation)
- **Used by**: `_looks_gibberish()`
- **Purpose**: Detect obviously invalid input
- **Impact**: Generic, but coupled to shopping validation

### Summary

- **C (Fake-store-specific)**: 0 lines
- **B (Shopping-specific)**: ~70 lines (verb detection, task validation, gibberish detection)
- **A (Generic)**: ~1 line (gibberish regex - but shopping-coupled)

### Refactor Plan

1. Make task interpretation generic (remove shopping verb gating)
2. Extract shopping-specific validation to optional domain skill
3. Keep generic input validation (gibberish detection)
4. Allow arbitrary task goals (not just shopping)
5. Make intent parsing optional and extensible

---

## 4. search_query.py (506 lines)

### Overview
Extracts short search queries from conversational user tasks using hardcoded term lists.

### Hardcoded Dependencies

#### B. Shopping-specific intelligence

**Line 9-127: _SEARCH_STOPWORDS**
```python
_SEARCH_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        # ... 100+ stopwords including shopping terms
        "add",
        "cart",
        "checkout",
        "rating",
        "ratings",
        "rated",
        "stars",
        "reviews",
        # ...
    }
)
```
- **Type**: B (Shopping-enriched stopwords)
- **Used by**: `extract_search_query()`
- **Purpose**: Filter conversational filler
- **Impact**: Hardcoded shopping vocabulary

**Line 130-131: _GARBAGE_TOKENS**
```python
_GARBAGE_TOKENS = frozenset({"ok", "okay", "go", "um", "uh", "hmm", "ya", "yeah", "nah"})
```
- **Type**: A (Generic ASR noise detection)
- **Used by**: `extract_search_query()`
- **Purpose**: Filter voice recognition noise
- **Impact**: Generic

**Line 133-148: _MODIFIER_WORDS**
```python
_MODIFIER_WORDS = frozenset(
    {
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
    }
)
```
- **Type**: B (Shopping-specific product modifiers)
- **Used by**: `extract_search_query()`
- **Purpose**: Deprioritize modifier words in queries
- **Impact**: Hardcoded e-commerce vocabulary

**Line 150-162: _CANONICAL_FORMS**
```python
_CANONICAL_FORMS = {
    "earbud": "earbuds",
    "earbuds": "earbuds",
    "headphone": "headphones",
    # ... product singular/plural mappings
}
```
- **Type**: B (Shopping-specific product normalization)
- **Used by**: `extract_search_query()`, `expand_search_token()`
- **Purpose**: Normalize product terms
- **Impact**: Hardcoded product vocabulary

**Line 164-178: _TERM_SYNONYMS**
```python
_TERM_SYNONYMS = {
    "earbud": ("earbud", "earbuds", "buds", "tws"),
    "headphone": ("headphone", "headphones", "headset", "rockerz"),
    # ... brand-specific and category synonyms
}
```
- **Type**: B (Shopping-specific product synonyms)
- **Used by**: `expand_search_token()`
- **Purpose**: Expand search terms for matching
- **Impact**: Hardcoded product/brand vocabulary

**Line 180-230: _PRODUCT_TERMS**
```python
_PRODUCT_TERMS = (
    "shampoo",
    "chocolates",
    "chocolate",
    "chips",
    "cookies",
    "dress",
    "dresses",
    "shoes",
    "sneakers",
    "headphones",
    "earbuds",
    # ... 50+ product terms
)
```
- **Type**: B (Shopping-specific product vocabulary)
- **Used by**: `_is_product_term()`, query extraction
- **Purpose**: Identify product terms in conversational input
- **Impact**: Hardcoded product catalog

**Line 304-319: _LIST_FILLER_PARTS, _QUERY_ALIASES**
```python
_LIST_FILLER_PARTS = frozenset(
    {
        "all",
        "everything",
        "anything",
        "etc",
        "stuff",
        # ...
    }
)

_QUERY_ALIASES = {
    "bars": "beauty bar",
    "bar": "beauty bar",
    "buds": "earbuds",
    # ...
}
```
- **Type**: B (Shopping-specific shopping list processing)
- **Used by**: `extract_product_queries()`
- **Purpose**: Parse shopping lists into individual queries
- **Impact**: Hardcoded shopping vocabulary

#### A. Generic browser capabilities

**Line 233-242: expand_search_token()**
```python
def expand_search_token(token: str) -> tuple[str, ...]:
    forms = {token, _canonicalize_token(token)}
    synonyms = _TERM_SYNONYMS.get(token) or _TERM_SYNONYMS.get(token.rstrip("s"))
    if synonyms:
        forms.update(synonyms)
    return tuple(forms)
```
- **Type**: A (Generic token expansion logic - but uses shopping synonyms)
- **Used by**: Query equivalence checking
- **Purpose**: Expand tokens for matching
- **Impact**: Generic logic, shopping data

**Line 275-301: search_queries_equivalent()**
```python
def search_queries_equivalent(left: str, right: str) -> bool:
    """True when two search strings target the same catalog intent."""
    a = extract_search_query(left).lower().strip()
    b = extract_search_query(right).lower().strip()
    # ... equivalence logic using token expansion
```
- **Type**: A (Generic query equivalence - but shopping-coupled)
- **Used by**: Goal verification, duplicate detection
- **Purpose**: Determine if queries target same intent
- **Impact**: Generic logic, shopping assumptions

**Line 431-476: extract_search_query()**
```python
def extract_search_query(task: str) -> str:
    """Turn chatty user goals into a short store search query."""
    text = task.strip().lower()
    text = re.sub(r"[^\w\s\-+&]", " ", text)
    text = _strip_budget_fragments(text)
    # ... stopword removal, product term prioritization
```
- **Type**: B (Shopping-specific query extraction)
- **Used by**: Throughout shopping logic
- **Purpose**: Convert conversational input to search queries
- **Impact**: Hardcoded shopping vocabulary and patterns

### Summary

- **C (Fake-store-specific)**: 0 lines
- **B (Shopping-specific)**: ~450 lines (vocabularies, synonyms, product terms, query extraction)
- **A (Generic)**: ~56 lines (token expansion, query equivalence - but shopping-coupled)

### Refactor Plan

1. Extract generic token expansion logic (decouple from shopping synonyms)
2. Make query extraction optional and domain-specific
3. Move shopping vocabularies to optional domain skill
4. Keep generic stopword removal as utility
5. Allow arbitrary query patterns (not just shopping)

---

## 5. shopping_intent.py (264 lines)

### Overview
Parses structured shopping constraints (budget, rating, quantity) from natural language.

### Hardcoded Dependencies

#### B. Shopping-specific intelligence

**Line 55-66: _BUDGET_PATTERNS**
```python
_BUDGET_PATTERNS = (
    re.compile(
        r"\b(?:under|below|less than|upto|up to|max(?:imum)?)\s*"
        r"(?:₹|rs\.?|inr|\$|usd)?\s*([\d,]+(?:\.\d+)?)\b",
        re.I,
    ),
    # ... more budget patterns
)
```
- **Type**: B (Shopping-specific budget parsing)
- **Used by**: `_extract_budget()`
- **Purpose**: Parse budget constraints
- **Impact**: Shopping-specific currency and pattern assumptions

**Line 68-73: _RATING_PATTERNS**
```python
_RATING_PATTERNS = (
    re.compile(r"\b(?:rating|rated|stars?)\s*(?:of\s*)?(?:at least\s*)?(\d(?:\.\d)?)\+?\b", re.I),
    re.compile(r"\b(\d(?:\.\d)?)\+?\s*stars?\b", re.I),
    re.compile(r"\bgood ratings?\b", re.I),
    re.compile(r"\bhigh(?:ly)?\s*rated\b", re.I),
)
```
- **Type**: B (Shopping-specific rating parsing)
- **Used by**: `_extract_min_rating()`
- **Purpose**: Parse rating constraints
- **Impact**: Shopping-specific 5-star rating system

**Line 75-78: _QTY_PATTERN**
```python
_QTY_PATTERN = re.compile(
    r"\b(?:qty|quantity|buy|get|need|want)?\s*(\d+)\s*(?:x|pcs?|pieces?|items?|units?)?\b",
    re.I,
)
```
- **Type**: B (Shopping-specific quantity parsing)
- **Used by**: `_extract_quantity()`
- **Purpose**: Parse quantity constraints
- **Impact**: Shopping-specific unit assumptions

**Line 80-108: _BRAND_HINTS**
```python
_BRAND_HINTS = frozenset(
    {
        "gucci",
        "nike",
        "adidas",
        "puma",
        "apple",
        "samsung",
        "sony",
        # ... 30+ brand names
    }
)
```
- **Type**: B (Shopping-specific brand detection)
- **Used by**: `_extract_brand()`
- **Purpose**: Detect brand mentions
- **Impact**: Hardcoded brand catalog

**Line 110-125: _PREFERENCE_KEYWORDS**
```python
_PREFERENCE_KEYWORDS = (
    ("discounted", "discount"),
    ("on sale", "sale"),
    ("deal", "deal"),
    ("offer", "offer"),
    ("wireless", "wireless"),
    ("bluetooth", "bluetooth"),
    # ... product feature preferences
)
```
- **Type**: B (Shopping-specific preference parsing)
- **Used by**: `_extract_preferences()`
- **Purpose**: Parse product feature preferences
- **Impact**: Hardcoded e-commerce vocabulary

**Line 218-264: parse_shopping_intent()**
```python
def parse_shopping_intent(task: str) -> ShoppingIntent:
    """Parse a user shopping task into structured constraints + short search query."""
    raw = task.strip()
    search_query = extract_search_query(raw)
    product = search_query or raw[:40]
    brand = _extract_brand(raw, search_query)
    budget_max = _extract_budget(raw)
    prefer_cheapest = bool(
        re.search(r"\b(cheapest|lowest price|lowest cost|most affordable)\b", raw, re.I)
    )
    prefer_discount = bool(
        re.search(r"\b(discount|discounted|on sale|deal|offer|cheap(?:er)?)\b", raw, re.I)
    )
    min_rating = _extract_min_rating(raw)
    quantity = _extract_quantity(raw)
    preferences = _extract_preferences(raw)

    confidence = 0.35
    # ... confidence scoring
```
- **Type**: B (Shopping-specific intent parsing)
- **Used by**: Browser Use prompt, product comparison
- **Purpose**: Extract shopping constraints
- **Impact**: Shopping-only constraint extraction

#### A. Generic browser capabilities

**Line 128-130: _parse_money()**
```python
def _parse_money(raw: str) -> float:
    return float(raw.replace(",", ""))
```
- **Type**: A (Generic number parsing)
- **Used by**: Budget extraction
- **Purpose**: Parse currency values
- **Impact**: Generic, but shopping-coupled

**Line 132-136: _detect_currency()**
```python
def _detect_currency(task: str) -> str:
    lowered = task.lower()
    if "$" in task or "usd" in lowered:
        return "USD"
    return "INR"
```
- **Type**: B (Shopping-specific currency detection - limited to INR/USD)
- **Used by**: Shopping intent
- **Purpose**: Detect currency from task
- **Impact**: Limited currency support

### Summary

- **C (Fake-store-specific)**: 0 lines
- **B (Shopping-specific)**: ~250 lines (patterns, brands, preferences, intent parsing)
- **A (Generic)**: ~3 lines (money parsing - shopping-coupled)

### Refactor Plan

1. Extract generic number/currency parsing
2. Make shopping intent parsing optional
3. Move shopping patterns to optional domain skill
4. Remove hardcoded brand catalog
5. Allow arbitrary constraint parsing (not just shopping)

---

## 6. heuristics.py (609 lines)

### Overview
Deterministic planning shortcuts to avoid unnecessary LLM calls.

### Hardcoded Dependencies

#### C. Fake-store-specific behavior

**Line 32-36: _SHOP_HINT regex**
```python
_SHOP_HINT = re.compile(
    r"\b(buy|find|search|cheapest|cheap|lowest|price|cart|order|shop|purchase|"
    r"checkout|amazon|flipkart|chocolates?|shampoo|product|add to cart|"
    r"rating|rated|stars?|reviews?|dress(?:es)?|party|help|want|need)\b",
    re.I,
)
```
- **Type**: B (Shopping-specific)
- **Used by**: `try_heuristic_plan()` gating
- **Purpose**: Enable heuristics for shopping tasks
- **Impact**: Mentions Amazon/Flipkart but not used for them

**Line 218-235: URL pattern detection**
```python
def _url_looks_like_product(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(
        token in path
        for token in ("/dp/", "/gp/product", "/product/", "/p/", "/item/")
    )

def _url_looks_like_results(url: str) -> bool:
    if _url_looks_like_product(url):
        return False
    parsed = urlparse(url)
    path = parsed.path.path.lower()
    query = parse_qs(parsed.query)
    if "k" in query or "q" in query or "field-keywords" in query:
        return True
    return any(token in path for token in ("/s", "/search", "/results", "/catalog"))

def _url_looks_like_cart(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(token in path for token in ("/cart", "/bag", "/basket", "/gp/cart"))

def _url_looks_like_checkout(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(token in path for token in ("/checkout", "/buy", "/payment", "/spc/"))
```
- **Type**: C (Fake-store + Amazon/Flipkart patterns)
- **Used by**: Heuristic planning logic
- **Purpose**: Detect page types from URL
- **Impact**: Hardcoded URL patterns for specific sites

**Line 274-307: _amount_paise_from_page()**
```python
def _amount_paise_from_page(page: PageContext) -> int | None:
    for element in page.elements:
        if element.tag == "data-rf-order-total" or "order total" in element.aria_label.lower():
            value = _parse_price(element.text)
            if value is not None:
                return int(round(value * 100))

    total_match = re.search(
        r"total[^\d₹$]*([\d,]+(?:\.\d{2})?)",
        " ".join(
            part
            for part in (
                page.title,
                *(element.text for element in page.elements[:12]),
            )
            if part
        ),
        re.I,
    )
    # ... fallback to product prices
```
- **Type**: C (Fake-store-specific: `data-rf-order-total`)
- **Used by**: Payment proposal heuristics
- **Purpose**: Extract order total for payment
- **Impact**: Hardcoded attribute and INR assumption

#### B. Shopping-specific intelligence

**Line 185-216: _pick_product()**
```python
def _pick_product(
    products: list[PageProductSummary],
    *,
    prefer_cheapest: bool,
    require_good_rating: bool,
) -> PageProductSummary | None:
    if not products:
        return None

    candidates = products
    if require_good_rating:
        rated = [
            product
            for product in products
            if (_parse_rating(product.rating_text) or 0) >= _MIN_GOOD_RATING
        ]
        if rated:
            candidates = rated

    if not prefer_cheapest:
        return candidates[0]

    priced: list[tuple[float, PageProductSummary]] = []
    for product in candidates:
        value = _parse_price(product.price_text)
        if value is not None:
            priced.append((value, product))
    if not priced:
        return candidates[0]
    priced.sort(key=lambda item: item[0])
    return priced[0][1]
```
- **Type**: B (Shopping-specific product selection)
- **Used by**: `try_heuristic_plan()`
- **Purpose**: Select product based on price/rating
- **Impact**: Hardcoded shopping decision logic

**Line 394-609: try_heuristic_plan()**
```python
def try_heuristic_plan(session: RunSession) -> PlannerChunkOutput | None:
    """Return a deterministic next chunk when the page state is unambiguous."""
    page = session.latest_page_context
    if page is None or not _SHOP_HINT.search(session.task):
        return None

    if _last_action_failed(session):
        return _recover_after_failure(session, page)

    query = extract_search_query(session.task)
    prefer_cheapest = bool(_CHEAPEST_HINT.search(session.task))
    require_good_rating = bool(_RATING_HINT.search(session.task))

    # ... element finding, action planning
    # ... login detection, OTP detection
    # ... checkout flow, cart navigation
    # ... product selection
```
- **Type**: B (Shopping-specific heuristic planning)
- **Used by**: Legacy planner
- **Purpose**: Generate deterministic plans for shopping tasks
- **Impact**: Hardcoded shopping workflow

**Line 451-463: Login/OTP detection**
```python
if re.search(r"sign[\s-]?in|log[\s-]?in|ap/signin|/login", page.url, re.I):
    logger.info("Heuristic: wait_for_user login runId=%s", session.run_id)
    return PlannerChunkOutput(
        steps=[WaitForUserStep(action="wait_for_user")],
        terminal="wait_for_user",
    )

if re.search(r"otp|captcha|verify.*(code|identity)", page.title, re.I):
    logger.info("Heuristic: wait_for_user verification runId=%s", session.run_id)
    return PlannerChunkOutput(
        steps=[WaitForUserStep(action="wait_for_user")],
        terminal="wait_for_user",
    )
```
- **Type**: A (Generic auth detection - but hardcoded patterns)
- **Used by**: Handoff triggering
- **Purpose**: Detect pages requiring user input
- **Impact**: Generic intent, hardcoded patterns

#### A. Generic browser capabilities

**Line 69-94: Element finding helpers**
```python
def _element_label(element: PageElementSummary) -> str:
    return " ".join(
        part
        for part in (element.text, element.placeholder, element.aria_label)
        if part
    ).lower()

def _indexed(element: PageElementSummary, position: int) -> int:
    return element.index if element.index > 0 else position

def _find_element(
    page: PageContext,
    *,
    role: str | None = None,
    text_hint: re.Pattern[str] | None = None,
) -> tuple[PageElementSummary, int] | None:
    # ... element finding logic
```
- **Type**: A (Generic element utilities)
- **Used by**: Heuristic planning
- **Purpose**: Find elements by role/text
- **Impact**: Generic capabilities

**Line 97-105: URL query extraction**
```python
def _url_search_query(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("q", "k", "query", "search"):
        values = query.get(key)
        if values and values[0].strip():
            return values[0].strip()
    return ""
```
- **Type**: A (Generic URL parsing)
- **Used by**: Query tracking, duplicate detection
- **Purpose**: Extract search query from URL
- **Impact**: Generic, but shopping-coupled

**Line 338-391: _recover_after_failure()**
```python
def _recover_after_failure(session: RunSession, page: PageContext) -> PlannerChunkOutput | None:
    last = session.history[-1]
    step = last.step

    if isinstance(step, ClickElementStep) and step.match_text:
        # Try next product link if previous product open failed.
        if page.products and step.role == "link":
            used = {
                entry.step.match_text.lower()
                for entry in session.history
                if isinstance(entry.step, ClickElementStep) and entry.step.match_text
            }
            for product in page.products:
                if product.title[:40].lower() in used:
                    continue
                target = _product_click_target(page, product)
                if target is None:
                    continue
                # ... retry logic
```
- **Type**: B (Shopping-specific recovery - product retry)
- **Used by**: `try_heuristic_plan()`
- **Purpose**: Recover from failed product clicks
- **Impact**: Hardcoded shopping recovery logic

### Summary

- **C (Fake-store-specific)**: ~80 lines (URL patterns, custom attributes, INR assumption)
- **B (Shopping-specific)**: ~400 lines (product selection, workflow logic, shopping recovery)
- **A (Generic)**: ~129 lines (element utilities, URL parsing, auth detection - but shopping-coupled)

### Refactor Plan

1. Extract generic element utilities to core
2. Extract generic URL parsing to core
3. Make auth detection pattern-based and extensible
4. Move shopping-specific heuristics to optional domain skill
5. Remove hardcoded URL patterns
6. Make recovery logic generic (not product-specific)

---

## Summary of All Hardcoded Dependencies

### C. Fake-store-specific behavior (~310 lines)
- URL gating (`is_razorflow_store_url()`)
- Hardcoded URL patterns (`/search`, `/cart`, `/checkout`)
- Custom attributes (`data-rf-auth-required`, `data-rf-order-total`)
- Category labels
- INR currency assumption

### B. Shopping-specific intelligence (~1,370 lines)
- Shopping verb detection
- Product vocabularies and synonyms
- Brand catalogs
- Budget/rating/quantity parsing
- Shopping workflow logic
- Product selection algorithms
- Shopping-specific recovery

### A. Generic browser capabilities (~303 lines - but shopping-coupled)
- Element utilities
- URL parsing
- Token expansion
- Query equivalence
- Auth detection
- Goal enforcement
- Loop detection

## Refactor Priority

1. **HIGH**: Remove URL gating and hardcoded patterns (C)
2. **HIGH**: Decouple generic utilities from shopping data (A)
3. **MEDIUM**: Make shopping intent parsing optional (B)
4. **MEDIUM**: Move shopping vocabularies to domain skill (B)
5. **LOW**: Generalize auth detection patterns (A/B)

## Target Architecture

```
Core Agent (Generic)
├── Task interpretation (generic)
├── Browser observation (generic)
├── LLM planning (generic)
├── Action execution (generic)
├── Goal verification (generic)
├── Recovery (generic)
└── Loop detection (generic)

Optional Domain Skills
├── Shopping intent parser
├── Shopping vocabularies
├── Shopping workflow heuristics
├── Product comparison
└── Store-specific optimizations
```

## Next Steps

1. Create generic utilities module
2. Extract generic capabilities from shopping code
3. Make shopping logic optional and pluggable
4. Remove URL gating
5. Build generic benchmark
6. Test on arbitrary sites
