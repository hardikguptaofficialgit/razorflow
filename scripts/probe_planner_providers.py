"""Probe each planner LLM provider and report which ones work."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "agent-backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(BACKEND / ".env", override=True)

from core import planner_llm  # noqa: E402

SYSTEM = "Return valid JSON only with keys actions (array) and reasoning (string)."
USER = "User wants to search for earbuds. Return one search action."

PROVIDERS = ("openrouter", "groq", "vercel_ai_gateway", "gemini")


def probe(provider: str) -> tuple[bool, str]:
    try:
        raw = planner_llm._complete_with_provider(provider, SYSTEM, USER)
        return True, raw[:80].replace("\n", " ")
    except Exception as error:
        return False, str(error).split("\n")[0][:120]


def main() -> None:
    working: list[str] = []
    print("Provider probe results:")
    for provider in PROVIDERS:
        ok, detail = probe(provider)
        status = "OK" if ok else "FAIL"
        print(f"  {provider:20} {status:4}  {detail}")
        if ok:
            working.append(provider)

    if working:
        print(f"\nRecommended default: {working[0]}")
    else:
        print("\nNo working provider found.")


if __name__ == "__main__":
    main()
