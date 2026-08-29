"""One-shot LLM failure E2E (backend must have AGENT_LLM_TEST_FIXTURE set)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.agent.ws_harness import run_ws_task

FIXTURE = ROOT / "tests" / "agent" / "fixtures" / "target_resolution_page.html"


async def main() -> int:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(FIXTURE.as_uri(), wait_until="domcontentloaded")

        result = await run_ws_task(
            page,
            "add Galaxy Buds FE to my cart",
            max_steps=10,
            step_timeout_s=60,
        )
        await browser.close()

    print(f"terminal={result.terminal} steps={result.steps} messages={len(result.messages)}")
    types = [m.get("type") for m in result.messages]
    print(f"message_types={types}")

    if result.terminal == "RUN_COMPLETE" and result.steps < 2:
        print("FAIL: false DONE from empty/finish proposal without recovery")
        return 1
    if result.terminal not in {"RUN_COMPLETE", "RUN_ERROR", "RUN_WAITING_FOR_USER"}:
        print(f"FAIL: unexpected terminal {result.terminal}")
        return 1
    if result.steps < 1:
        print("FAIL: no steps executed — recovery did not replan")
        return 1
    print("PASS: LLM failure recovery E2E")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
