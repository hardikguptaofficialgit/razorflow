"""Check OpenRouter key status and account credits (no secrets printed)."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent-backend"))

from utils.config import get_openrouter_api_keys, load_environment  # noqa: E402


def _get(url: str, api_key: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    load_environment()
    keys = get_openrouter_api_keys()
    if not keys:
        print("OPENROUTER: no API keys configured in .env")
        return 1

    print(f"OPENROUTER: {len(keys)} key(s) configured")
    for index, key in enumerate(keys, start=1):
        try:
            payload = _get("https://openrouter.ai/api/v1/key", key)
            data = payload.get("data", payload)
            label = str(data.get("label", "?"))
            if label.startswith("sk-or-"):
                label = "sk-or-…" + label[-4:] if len(label) > 8 else "[redacted]"
            usage = data.get("usage")
            limit = data.get("limit")
            remaining = data.get("limit_remaining")
            print(
                f"  key #{index}: label={label!r} "
                f"usage={usage} limit={limit} limit_remaining={remaining}"
            )
        except urllib.error.HTTPError as error:
            body = error.read().decode(errors="replace")[:160]
            print(f"  key #{index}: HTTP {error.code} — {body}")
        except Exception as error:
            print(f"  key #{index}: failed — {error}")

    try:
        payload = _get("https://openrouter.ai/api/v1/credits", keys[0])
        data = payload.get("data", payload)
        total = float(data.get("total_credits", 0))
        used = float(data.get("total_usage", 0))
        print(
            f"ACCOUNT: purchased=${total:.4f} used=${used:.4f} "
            f"remaining=${total - used:.4f}"
        )
    except urllib.error.HTTPError as error:
        if error.code in {401, 403}:
            print(
                "ACCOUNT: /credits needs a management key — "
                "use limit_remaining from /key above for this API key."
            )
        else:
            body = error.read().decode(errors="replace")[:160]
            print(f"ACCOUNT: HTTP {error.code} — {body}")
    except Exception as error:
        print(f"ACCOUNT: failed — {error}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
