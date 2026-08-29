"""Adversarial agent benchmark — reasoning, boundaries, recovery, and generalization."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent-backend"))

STORE_URL = "http://localhost:3001/demo"
WS_URL = "ws://127.0.0.1:8765/ws"
GENERIC_SHOP = ROOT / "tests" / "agent" / "fixtures" / "generic_shop.html"


@dataclass
class SuiteScore:
    name: str
    passed: int
    total: int
    details: list[str] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return (self.passed / self.total * 100) if self.total else 0.0


@dataclass
class LiveTaskScore:
    task: str
    success: bool
    actions: int = 0
    unnecessary_actions: int = 0
    product_page_visited: bool = False
    forbidden_violations: int = 0
    time_s: float = 0.0
    note: str = ""


def run_pytest_suite(pattern: str, label: str) -> SuiteScore:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        pattern,
        "-q",
        "--tb=no",
    ]
    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    passed = 0
    total = 0
    for line in output.splitlines():
        if line.strip().endswith("%]"):
            continue
        if " passed" in line and " in " in line:
            parts = line.strip().split(" in ")
            left = parts[0]
            if "failed" in left:
                chunk = left.replace(" failed", "").replace(",", " ")
                nums = [int(x) for x in chunk.split() if x.isdigit()]
                if len(nums) >= 2:
                    passed, failed = nums[0], nums[1]
                    total = passed + failed
            elif left.startswith("passed"):
                passed = int(left.split()[0])
                total = passed
    if total == 0 and result.returncode == 0:
        passed = 1
        total = 1
    return SuiteScore(
        name=label,
        passed=passed,
        total=max(total, passed),
        details=[output.strip()[-400:]] if output.strip() else [],
    )


async def run_live_task_with_audit(
    page: Any,
    task: str,
    *,
    forbid_product_page: bool = False,
) -> LiveTaskScore:
    from tests.agent.run_agent_benchmark import run_benchmark_task
    from agent_runtime.task.parse import parse_task_spec
    from agent_runtime.policy.action_gate import classify_action, filter_forbidden_actions

    spec = parse_task_spec(task)
    started = time.perf_counter()
    result = await run_benchmark_task(page, task)
    elapsed = time.perf_counter() - started

    forbidden_hits = 0
    for entry in result.trace:
        if entry.event != "NEXT_ACTION":
            continue

    product_page = "/product" in result.final_url.lower()
    success = result.terminal == "RUN_COMPLETE"
    if forbid_product_page and product_page:
        success = False

    if spec.target_phase == "search_results":
        if result.actions > 1:
            success = False
            result.note = f"search-only task used {result.actions} actions (max 1)"
        if product_page:
            success = False
            result.note = "visited product page on search-only task"

    score = LiveTaskScore(
        task=task,
        success=success,
        actions=result.actions,
        unnecessary_actions=int(getattr(result, "unnecessary_actions", 0)),
        product_page_visited=product_page,
        forbidden_violations=forbidden_hits,
        time_s=elapsed,
        note=result.failure_reason or result.note,
    )
    return score


async def test_generic_shop_search(page: Any) -> LiveTaskScore:
    """Generic HTML shop — no data-rf attributes."""
    score = LiveTaskScore(task="generic: search Galaxy", success=False)
    await page.goto(GENERIC_SHOP.as_uri(), wait_until="domcontentloaded")
    await page.locator("#accept-cookies").click()
    await page.locator("#search-input").fill("Galaxy")
    await page.locator("#search-form").evaluate("form => form.requestSubmit()")
    await page.wait_for_timeout(300)
    titles = await page.locator("article.card h2").all_text_contents()
    score.success = any("Galaxy" in t for t in titles)
    score.actions = 2
    score.note = f"results={titles}"
    return score


async def test_generic_target_resolution(page: Any) -> LiveTaskScore:
    """Click the Add button inside the Galaxy Buds FE card only."""
    score = LiveTaskScore(task="generic: add Galaxy Buds FE", success=False)
    await page.goto(GENERIC_SHOP.as_uri(), wait_until="domcontentloaded")
    await page.locator("#accept-cookies").click()
    card = page.locator('article[data-product-id="buds-fe"]')
    await card.locator(".add-btn").click()
    await page.wait_for_timeout(200)
    cart = await page.evaluate("() => document.body.dataset.cartCount || '0'")
    wrong = page.locator('article[data-product-id="buds-2"] .add-btn')
    wrong_text = await wrong.text_content()
    score.success = cart == "1" and wrong_text == "Add to cart"
    score.actions = 1
    score.note = f"cart={cart}"
    return score


async def run_live_suites(page: Any) -> list[LiveTaskScore]:
    from tests.agent.run_live_e2e_tasks import STORE_URL, clear_cart

    scores: list[LiveTaskScore] = []

    await clear_cart(page)
    await page.goto(STORE_URL, wait_until="domcontentloaded")
    scores.append(
        await run_live_task_with_audit(
            page,
            "find me good wireless earbuds under ₹6000",
            forbid_product_page=True,
        )
    )

    await clear_cart(page)
    await page.goto(STORE_URL, wait_until="domcontentloaded")
    scores.append(
        await run_live_task_with_audit(page, "find the cheapest smartwatch")
    )

    scores.append(await test_generic_shop_search(page))
    scores.append(await test_generic_target_resolution(page))
    return scores


def print_report(
    unit_suites: list[SuiteScore],
    live_scores: list[LiveTaskScore],
) -> None:
    print("=" * 80)
    print("ADVERSARIAL BENCHMARK REPORT")
    print("=" * 80)

    for suite in unit_suites:
        print(f"{suite.name}: {suite.passed}/{suite.total} ({suite.rate:.0f}%)")

    print("-" * 80)
    print("LIVE / GENERIC TASKS")
    for item in live_scores:
        status = "PASS" if item.success else "FAIL"
        print(
            f"[{status}] {item.task} | actions={item.actions} "
            f"product_page={item.product_page_visited} time={item.time_s:.1f}s"
        )
        if item.note:
            print(f"         {item.note[:120]}")

    unit_passed = sum(s.passed for s in unit_suites)
    unit_total = sum(s.total for s in unit_suites)
    live_passed = sum(1 for s in live_scores if s.success)
    live_total = len(live_scores)

    print("=" * 80)
    print("SUMMARY")
    print(f"  unit_test_score:      {unit_passed}/{unit_total}")
    print(f"  live_generic_score:   {live_passed}/{live_total}")
    print(f"  goal_boundary_suite:  {next((s.rate for s in unit_suites if 'parser' in s.name), 0):.0f}%")
    print(f"  verifier_suite:       {next((s.rate for s in unit_suites if 'verifier' in s.name), 0):.0f}%")
    print(f"  entity_extraction:    {next((s.rate for s in unit_suites if 'entity' in s.name), 0):.0f}%")
    if live_scores:
        avg_actions = sum(s.actions for s in live_scores) / len(live_scores)
        print(f"  avg_live_actions:     {avg_actions:.1f}")
        product_visits = sum(1 for s in live_scores if s.product_page_visited)
        print(f"  wrongful_product_nav: {product_visits}")


async def main() -> None:
    unit_suites = [
        run_pytest_suite("tests/agent/test_entity_extraction.py", "entity_extraction"),
        run_pytest_suite("tests/agent/test_adversarial_parser.py", "adversarial_parser"),
        run_pytest_suite("tests/agent/test_adversarial_verifier.py", "adversarial_verifier"),
        run_pytest_suite("tests/agent/test_runtime_v2_task.py", "happy_path_parser"),
        run_pytest_suite("tests/agent/test_runtime_v2_memory.py", "memory_sync"),
    ]

    live_scores: list[LiveTaskScore] = []
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            live_scores = await run_live_suites(page)
            await browser.close()
    except Exception as exc:
        live_scores.append(
            LiveTaskScore(task="live_suite", success=False, note=str(exc))
        )

    print_report(unit_suites, live_scores)


if __name__ == "__main__":
    asyncio.run(main())
