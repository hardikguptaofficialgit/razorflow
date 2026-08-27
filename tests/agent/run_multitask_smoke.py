"""Multi-task live smoke runner for fake-store Browser Use accuracy checks."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.shopping_intent import parse_shopping_intent  # noqa: E402

FAKE = os.getenv("FAKE_STORE_URL", "http://127.0.0.1:3000").rstrip("/")
TASKS = [
    "Buy me the cheapest shampoo with good ratings",
    "find chocolates under 100",
    "help me buy a gucci bag at discounted price",
]


async def run_task(task: str, timeout: int = 160) -> dict:
    import websockets

    run_id = f"mt-{uuid.uuid4().hex[:8]}"
    msgs: list[dict] = []
    async with websockets.connect("ws://127.0.0.1:8765/ws", open_timeout=10) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "START_RUN",
                    "runId": run_id,
                    "task": task,
                    "url": FAKE,
                },
            ),
        )
        end = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=50)
            except TimeoutError:
                break
            item = json.loads(raw)
            msgs.append(item)
            if (
                item.get("type")
                in {
                    "RUN_COMPLETE",
                    "RUN_ERROR",
                    "RUN_WAITING_FOR_USER",
                    "PAYMENT_LINK_CONFIRMATION_REQUIRED",
                }
                and item.get("runId") == run_id
            ):
                break
        await ws.send(json.dumps({"type": "CANCEL_RUN", "runId": run_id}))

    syncs = [m for m in msgs if m.get("type") == "AGENT_SYNC"]
    terminal = next(
        (
            m
            for m in reversed(msgs)
            if m.get("type")
            in {
                "RUN_COMPLETE",
                "RUN_ERROR",
                "RUN_WAITING_FOR_USER",
                "PAYMENT_LINK_CONFIRMATION_REQUIRED",
            }
        ),
        None,
    )
    return {
        "task": task,
        "sync_count": len(syncs),
        "first_sync": syncs[0].get("actionSummary") if syncs else None,
        "terminal": None
        if not terminal
        else {"type": terminal.get("type"), "message": terminal.get("message")},
        "urls": list({m.get("url") for m in syncs if m.get("url")})[:6],
    }


async def main() -> None:
    results = []
    for task in TASKS:
        intent = parse_shopping_intent(task)
        print(f"\n=== TASK: {task}")
        print(
            f"INTENT query={intent.search_query!r} cheapest={intent.prefer_cheapest} "
            f"rating={intent.min_rating} discount={intent.prefer_discount} brand={intent.brand}",
        )
        result = await run_task(task)
        results.append(result)
        print(
            f"RESULT syncs={result['sync_count']} terminal={result['terminal']} "
            f"first_sync={result['first_sync']!r}",
        )
        print(f"URLS={result['urls']}")

    fails = [
        r
        for r in results
        if not r["terminal"] or r["terminal"]["type"] == "RUN_ERROR" or r["sync_count"] < 1
    ]
    print("\nSUMMARY", {"ok": len(results) - len(fails), "fail": len(fails)})
    if fails:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
