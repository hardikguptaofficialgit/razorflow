"""Print planner/env readiness without exposing secrets."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "agent-backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(BACKEND / ".env", override=True)

from utils import config  # noqa: E402

checks = {
    "OPENROUTER_API_KEY": bool(config.get_openrouter_api_keys()),
    "GROQ_API_KEY": config.is_groq_configured(),
    "AI_GATEWAY_API_KEY": bool(os.getenv("AI_GATEWAY_API_KEY", "").strip()),
    "VERCEL_OIDC_TOKEN": bool(os.getenv("VERCEL_OIDC_TOKEN", "").strip()),
    "VERCEL_AI_GATEWAY_READY": config.is_vercel_ai_gateway_configured(),
    "GEMINI_API_KEY": config.is_gemini_configured(),
    "RAZORPAY": config.is_razorpay_configured(),
}

print("PLANNER_LLM_PROVIDER:", config.get_planner_llm_provider())
print("PLANNER_CHAIN:", " -> ".join(config.get_planner_llm_fallback_chain()))
print("PLANNER_READY:", config.is_planner_llm_ready())
for name, ok in checks.items():
    print(f"{name}: {'yes' if ok else 'no'}")
print("OPENROUTER_MODEL:", config.get_openrouter_model())
print("GROQ_MODEL:", config.get_groq_model())
print("VERCEL_GATEWAY_MODEL:", config.get_vercel_ai_gateway_model())
print("GEMINI_MODEL:", config.get_gemini_model())
