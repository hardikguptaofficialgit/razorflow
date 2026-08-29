"""Rich browser observation for LLM planning (site-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

from core.protocol import PageCartLineSummary, PageContext, PageElementSummary, PageProductSummary


@dataclass
class ObservedElement:
    element_id: str
    index: int
    role: str
    tag: str
    text: str
    placeholder: str
    aria_label: str
    href: str = ""
    value: str = ""
    visible: bool = True
    enabled: bool = True
    clickable: bool = False
    typeable: bool = False


@dataclass
class ObservedProduct:
    product_id: str
    title: str
    price_text: str
    rating_text: str
    add_element_id: str | None = None
    link_element_id: str | None = None


@dataclass
class ObservedCartLine:
    title: str
    quantity: int
    remove_element_id: str | None = None


@dataclass
class BrowserPage:
    title: str
    url: str
    path: str
    search_query: str
    elements: list[ObservedElement] = field(default_factory=list)
    products: list[ObservedProduct] = field(default_factory=list)
    cart_lines: list[ObservedCartLine] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)

    def signature(self) -> str:
        cart_qty = sum(line.quantity for line in self.cart_lines)
        el_sample = "|".join(
            f"{el.element_id}:{(el.text or el.aria_label)[:16]}"
            for el in self.elements[:20]
        )
        return (
            f"{self.url}|{len(self.products)}|{len(self.cart_lines)}|"
            f"cartqty:{cart_qty}|{len(self.elements)}|{el_sample[:200]}"
        )


def _element_id(index: int) -> str:
    return f"e{index}"


def _parse_search_query(url: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    values = parse_qs(parsed.query).get("q", [])
    return values[0] if values else ""


from agent_runtime.observation.cart_state import header_cart_item_count
from agent_runtime.observation.signals import infer_page_signals


def observe_from_page_context(page: PageContext | None) -> BrowserPage | None:
    if page is None:
        return None

    elements: list[ObservedElement] = []
    for el in page.elements[:100]:
        idx = el.index or len(elements) + 1
        role = el.role
        tag = el.tag
        text = (el.text or "")[:120]
        placeholder = (el.placeholder or "")[:80]
        aria = (el.aria_label or "")[:80]
        clickable = role in {"button", "link"} or tag in {"button", "a"}
        typeable = role in {"search", "input"} or tag in {"input", "textarea"}
        href = (getattr(el, "href", "") or "")[:200]
        value = (getattr(el, "value", "") or "")[:80]
        enabled = getattr(el, "enabled", True)
        bbox_x = getattr(el, "bbox_x", None)
        elements.append(
            ObservedElement(
                element_id=_element_id(idx),
                index=idx,
                role=role,
                tag=tag,
                text=text,
                placeholder=placeholder,
                aria_label=aria,
                href=href,
                value=value,
                visible=True,
                enabled=enabled,
                clickable=clickable,
                typeable=typeable,
            )
        )

    products: list[ObservedProduct] = []
    for i, product in enumerate(page.products[:32], start=1):
        products.append(
            ObservedProduct(
                product_id=f"p{i}",
                title=product.title,
                price_text=product.price_text,
                rating_text=product.rating_text,
                add_element_id=(
                    _element_id(product.add_to_cart_element_index)
                    if product.add_to_cart_element_index
                    else None
                ),
                link_element_id=(
                    _element_id(product.element_index)
                    if product.element_index
                    else None
                ),
            )
        )

    cart_lines = [
        ObservedCartLine(
            title=line.title,
            quantity=line.quantity,
            remove_element_id=(
                _element_id(line.remove_element_index)
                if line.remove_element_index
                else None
            ),
        )
        for line in page.cart_lines
    ]

    header_cart = header_cart_item_count(page)
    if not cart_lines and header_cart > 0:
        cart_lines = [
            ObservedCartLine(title="(header cart badge)", quantity=header_cart)
        ]

    path = urlparse(page.url).path if page.url else ""
    return BrowserPage(
        title=page.title or "",
        url=page.url or "",
        path=path,
        search_query=_parse_search_query(page.url or ""),
        elements=elements,
        products=products,
        cart_lines=cart_lines,
        signals=infer_page_signals(page),
    )


def format_observation(page: BrowserPage | None, *, max_elements: int = 60) -> str:
    if page is None:
        return "PAGE: (no observation yet)"

    lines = [
        f"URL: {page.url}",
        f"Title: {page.title}",
        f"Path: {page.path}",
    ]
    if page.search_query:
        lines.append(f"SearchQuery: {page.search_query}")
    if page.signals:
        lines.append(f"Signals: {', '.join(page.signals)}")

    if page.products:
        lines.append("\nProducts:")
        for product in page.products[:12]:
            add = f" add={product.add_element_id}" if product.add_element_id else ""
            link = f" link={product.link_element_id}" if product.link_element_id else ""
            lines.append(
                f"- {product.product_id}: {product.title} | {product.price_text}{add}{link}"
            )

    if page.cart_lines:
        lines.append("\nCart:")
        for line in page.cart_lines:
            rem = f" remove={line.remove_element_id}" if line.remove_element_id else ""
            lines.append(f"- {line.title} x{line.quantity}{rem}")

    lines.append("\nInteractive elements:")
    for el in page.elements[:max_elements]:
        label = el.text or el.aria_label or el.placeholder or el.tag
        flags = []
        if el.clickable:
            flags.append("click")
        if el.typeable:
            flags.append("type")
        flag_text = f" [{','.join(flags)}]" if flags else ""
        href_part = f" href={el.href}" if el.href else ""
        lines.append(
            f"- [{el.element_id}] {el.role}/{el.tag} \"{label[:80]}\"{flag_text}{href_part}"
        )
    if len(page.elements) > max_elements:
        lines.append(f"... ({len(page.elements) - max_elements} more elements)")

    return "\n".join(lines)
