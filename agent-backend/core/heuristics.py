"""Deterministic planning shortcuts to avoid unnecessary LLM calls."""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, urlparse

from core.protocol import (
    ClickElementStep,
    NavigateUrlStep,
    PageContext,
    PageElementSummary,
    PageProductSummary,
    PaymentLinkProposalPayload,
    PlannerChunkOutput,
    ReadyForPaymentLinkStep,
    TypeInElementStep,
    WaitForUserStep,
)
from core.run_manager import RunSession
from core.task_intent import (
    goal_allows_cart_nav,
    goal_allows_checkout,
    goal_allows_payment,
    parse_task_intent,
)
from core.search_query import expand_search_token, extract_search_query, looks_like_chatty_search

logger = logging.getLogger(__name__)

_SHOP_HINT = re.compile(
    r"\b(buy|find|search|cheapest|cheap|lowest|price|cart|order|shop|purchase|"
    r"checkout|amazon|flipkart|chocolates?|shampoo|product|add to cart|"
    r"rating|rated|stars?|reviews?|dress(?:es)?|party|help|want|need)\b",
    re.I,
)
_CHEAPEST_HINT = re.compile(r"\b(cheapest|lowest|least expensive|budget|affordable)\b", re.I)
_RATING_HINT = re.compile(r"\b(rating|rated|stars?|reviews?|highly rated|good ratings?)\b", re.I)
_PRICE_VALUE = re.compile(r"[\d,]+(?:\.\d+)?")
_MIN_GOOD_RATING = 4.0
_TASK_STOPWORDS = {
    "buy",
    "find",
    "search",
    "cheapest",
    "cheap",
    "lowest",
    "under",
    "price",
    "cart",
    "order",
    "shop",
    "purchase",
    "checkout",
    "product",
    "the",
    "for",
    "and",
    "with",
    "good",
    "best",
    "help",
    "want",
    "need",
}


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
    for position, element in enumerate(page.elements, start=1):
        if role and element.role != role:
            continue
        label = _element_label(element)
        if text_hint and not text_hint.search(label):
            continue
        return element, _indexed(element, position)
    return None


def _url_search_query(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("q", "k", "query", "search"):
        values = query.get(key)
        if values and values[0].strip():
            return values[0].strip()
    return ""


def _results_look_wrong(page: PageContext, query: str) -> bool:
    if not page.products or not query.strip():
        return False

    terms = [token for token in query.lower().split() if len(token) >= 2]
    if not terms:
        return False

    visible_titles = " ".join(product.title.lower() for product in page.products[:8])
    for token in terms:
        forms = expand_search_token(token)
        if any(form in visible_titles for form in forms):
            return False
    return True


def _needs_fresh_search(page: PageContext, query: str, searched: bool) -> bool:
    if not searched:
        return False

    url_query = _url_search_query(page.url)
    if url_query and looks_like_chatty_search(url_query):
        return True

    if _url_looks_like_results(page.url) and _results_look_wrong(page, query):
        return True

    return False


def _task_product_terms(task: str, query: str) -> list[str]:
    blob = f"{task} {query}".lower()
    tokens = re.findall(r"[a-z0-9]+", blob)
    return [token for token in tokens if len(token) >= 4 and token not in _TASK_STOPWORDS]


def _filter_products_for_task(
    products: list[PageProductSummary],
    task: str,
    query: str,
) -> list[PageProductSummary]:
    terms = _task_product_terms(task, query)
    if not terms:
        return products

    matched = [
        product
        for product in products
        if any(term in product.title.lower() for term in terms)
    ]
    return matched if matched else products


def _parse_price(price_text: str) -> float | None:
    match = _PRICE_VALUE.search(price_text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _parse_rating(rating_text: str | None) -> float | None:
    if not rating_text:
        return None
    match = re.search(r"(\d(?:\.\d)?)\s*(?:out of|/)?\s*5?", rating_text)
    if not match:
        match = re.search(r"(\d(?:\.\d)?)", rating_text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value if 0 < value <= 5 else None


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
    path = parsed.path.lower()
    query = parse_qs(parsed.query)
    if "k" in query or "q" in query or "field-keywords" in query:
        return True
    return any(token in path for token in ("/s", "/search", "/results", "/catalog"))


def _url_looks_like_cart(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(token in path for token in ("/cart", "/bag", "/basket", "gp/cart"))


def _url_looks_like_checkout(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(token in path for token in ("/checkout", "/buy", "/payment", "spc/"))


def _already_searched_for(session: RunSession, query: str) -> bool:
    needle = query.lower()
    for entry in session.history:
        step = entry.step
        if not entry.success:
            continue
        if isinstance(step, NavigateUrlStep):
            url_query = _url_search_query(step.url)
            if url_query and (
                needle in url_query.lower() or url_query.lower() in needle
            ):
                return True
            continue
        if not isinstance(step, TypeInElementStep):
            continue
        typed = step.text.strip().lower()
        if looks_like_chatty_search(typed):
            continue
        if needle in typed or typed in needle:
            return True
    return False


def _last_action_failed(session: RunSession) -> bool:
    return bool(session.history) and not session.history[-1].success


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
    if total_match:
        value = _parse_price(total_match.group(1))
        if value is not None:
            return int(round(value * 100))

    prices = [
        _parse_price(product.price_text)
        for product in page.products
        if product.price_text
    ]
    prices = [price for price in prices if price is not None]
    if not prices:
        return None
    rupees = max(prices)
    return int(round(rupees * 100))


def _product_click_target(
    page: PageContext,
    product: PageProductSummary,
) -> tuple[PageElementSummary, int] | None:
    if product.add_to_cart_element_index and product.add_to_cart_element_index > 0:
        for position, element in enumerate(page.elements, start=1):
            index = _indexed(element, position)
            if index == product.add_to_cart_element_index:
                return element, index

    if product.element_index and product.element_index > 0:
        for position, element in enumerate(page.elements, start=1):
            index = _indexed(element, position)
            if index == product.element_index:
                return element, index

    title_hint = re.compile(re.escape(product.title[:24]), re.I)
    add_button = _find_element(
        page,
        role="button",
        text_hint=re.compile(r"add to cart|buy now", re.I),
    )
    if add_button:
        return add_button

    return _find_element(page, role="link", text_hint=title_hint)


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
                _element, index = target
                logger.info("Heuristic recovery: next product runId=%s", session.run_id)
                return PlannerChunkOutput(
                    steps=[
                        ClickElementStep(
                            action="click_element",
                            role="link",
                            element_index=index,
                            match_text=product.title[:40],
                        ),
                    ],
                    terminal="continue",
                )

        if re.search(r"search|go|submit|find", step.match_text, re.I):
            search_button = _find_element(
                page,
                role="button",
                text_hint=re.compile(r"search|go|submit|find", re.I),
            )
            if search_button:
                _button, button_index = search_button
                logger.info("Heuristic recovery: search button runId=%s", session.run_id)
                return PlannerChunkOutput(
                    steps=[
                        ClickElementStep(
                            action="click_element",
                            role="button",
                            element_index=button_index,
                            match_text="search",
                        ),
                    ],
                    terminal="continue",
                )

    return None


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

    search_match = _find_element(page, role="search") or _find_element(
        page,
        role="input",
        text_hint=re.compile(r"search|query|find", re.I),
    )
    search_button = _find_element(
        page,
        role="button",
        text_hint=re.compile(r"search|go|submit|find", re.I),
    )
    add_to_cart = _find_element(
        page,
        role="button",
        text_hint=re.compile(r"add to cart|add to basket|buy now", re.I),
    )
    cart_link = _find_element(
        page,
        text_hint=re.compile(r"^(cart|bag|basket|go to cart|view cart)", re.I),
    ) or _find_element(
        page,
        role="link",
        text_hint=re.compile(r"cart|bag|basket", re.I),
    )
    checkout = _find_element(
        page,
        role="button",
        text_hint=re.compile(
            r"proceed to checkout|proceed to buy|place order|checkout|buy now|pay now",
            re.I,
        ),
    ) or _find_element(
        page,
        role="link",
        text_hint=re.compile(r"proceed to checkout|checkout|place order", re.I),
    )

    on_product = _url_looks_like_product(page.url) or bool(add_to_cart and not page.products)
    on_results = _url_looks_like_results(page.url)
    on_cart = _url_looks_like_cart(page.url)
    on_checkout = _url_looks_like_checkout(page.url)
    searched = _already_searched_for(session, query)
    if _needs_fresh_search(page, query, searched):
        searched = False

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

    task_intent = parse_task_intent(session.task)

    if on_checkout and checkout is None and goal_allows_payment(task_intent.goal):
        amount = _amount_paise_from_page(page)
        if amount and amount > 0:
            title = page.products[0].title[:60] if page.products else "Checkout"
            logger.info("Heuristic: ready_for_payment_link runId=%s", session.run_id)
            return PlannerChunkOutput(
                steps=[
                    ReadyForPaymentLinkStep(
                        action="ready_for_payment_link",
                        title=title,
                        description=session.task[:120],
                        amount_paise=amount,
                        currency="INR",
                    ),
                ],
                terminal="ready_for_payment_link",
                payment_proposal=PaymentLinkProposalPayload(
                    title=title,
                    description=session.task[:120],
                    amount_paise=amount,
                    currency="INR",
                ),
            )

    if checkout and (on_cart or on_checkout) and goal_allows_checkout(parse_task_intent(session.task).goal):
        _element, index = checkout
        logger.info("Heuristic: checkout runId=%s", session.run_id)
        return PlannerChunkOutput(
            steps=[
                ClickElementStep(
                    action="click_element",
                    role=_element.role,
                    element_index=index,
                    match_text=_element_label(_element)[:40] or "checkout",
                ),
            ],
            terminal="continue",
        )

    if on_cart and cart_link is None and checkout is None:
        # Already on cart with no clear checkout control — let LLM decide.
        return None

    # After add-to-cart success, open cart only when the user goal requires it.
    task_goal = parse_task_intent(session.task).goal
    if cart_link and (on_product or on_results) and goal_allows_cart_nav(task_goal):
        last_ok = session.history and session.history[-1].success
        last_step = session.history[-1].step if session.history else None
        if last_ok and isinstance(last_step, ClickElementStep):
            if last_step.match_text and re.search(
                r"add to cart|buy now", last_step.match_text, re.I
            ):
                _element, index = cart_link
                logger.info("Heuristic: open cart runId=%s", session.run_id)
                return PlannerChunkOutput(
                    steps=[
                        ClickElementStep(
                            action="click_element",
                            role=_element.role,
                            element_index=index,
                            match_text="cart",
                        ),
                    ],
                    terminal="continue",
                )

    if add_to_cart and on_product:
        _element, index = add_to_cart
        logger.info("Heuristic: add_to_cart runId=%s", session.run_id)
        return PlannerChunkOutput(
            steps=[
                ClickElementStep(
                    action="click_element",
                    role="button",
                    element_index=index,
                    match_text="add to cart",
                ),
            ],
            terminal="continue",
        )

    if on_results and page.products and (
        searched or _url_looks_like_results(page.url)
    ):
        scoped_products = _filter_products_for_task(page.products, session.task, query)
        target = _pick_product(
            scoped_products,
            prefer_cheapest=prefer_cheapest,
            require_good_rating=require_good_rating,
        )
        if target is None:
            return None

        product_link = _product_click_target(page, target)
        if product_link is None:
            return None

        _element, index = product_link
        is_add_to_cart = _element.role == "button" and bool(
            re.search(r"add to cart|buy now", _element_label(_element), re.I),
        )
        click_index = index
        if is_add_to_cart and target.add_to_cart_element_index:
            click_index = target.add_to_cart_element_index
            for position, element in enumerate(page.elements, start=1):
                el_index = _indexed(element, position)
                if el_index == click_index:
                    _element = element
                    break
        logger.info(
            "Heuristic: %s product '%s' runId=%s",
            "add_to_cart" if is_add_to_cart else "open",
            target.title[:40],
            session.run_id,
        )
        return PlannerChunkOutput(
            steps=[
                ClickElementStep(
                    action="click_element",
                    role=_element.role,
                    element_index=click_index,
                    match_text=(
                        "add to cart"
                        if is_add_to_cart
                        else target.title[:40]
                    ),
                ),
            ],
            terminal="continue",
        )

    if search_match and (
        not searched or _needs_fresh_search(page, query, searched)
    ):
        search_field, index = search_match
        logger.info("Heuristic: type search '%s' runId=%s", query, session.run_id)
        steps: list = [
            TypeInElementStep(
                action="type_in_element",
                role="search" if search_field.role == "search" else "input",
                text=query,
                element_index=index,
            ),
        ]
        if search_button and search_field.role != "search":
            _button, button_index = search_button
            steps.append(
                ClickElementStep(
                    action="click_element",
                    role="button",
                    element_index=button_index,
                    match_text="search",
                ),
            )
        return PlannerChunkOutput(steps=steps, terminal="continue")

    if search_button and searched and not page.products:
        _button, button_index = search_button
        logger.info("Heuristic: click search button runId=%s", session.run_id)
        return PlannerChunkOutput(
            steps=[
                ClickElementStep(
                    action="click_element",
                    role="button",
                    element_index=button_index,
                    match_text="search",
                ),
            ],
            terminal="continue",
        )

    return None
