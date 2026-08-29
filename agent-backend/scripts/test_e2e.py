"""Simple E2E test - sends task through WebSocket to agent backend."""

import asyncio
import websockets
import json
import sys
import os
from pathlib import Path

# Add paths
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_BACKEND_ROOT))

# Set environment BEFORE importing config (config loads env at import time)
# Use browser-use executor for standalone execution
os.environ["AGENT_RUNTIME_V2"] = "false"
os.environ["BROWSER_USE_EXECUTOR_ENABLED"] = "true"
os.environ["BROWSER_USE_HEADLESS"] = "false"
os.environ["BROWSER_USE_INCLUDE_SCREENSHOT"] = "true"
os.environ["PLANNER_INCLUDE_SCREENSHOT"] = "true"
os.environ["MAX_BROWSER_USE_STEPS"] = "40"
os.environ["BROWSER_USE_CDP_URL"] = ""  # Let browser-use auto-launch Chrome

# Force reload of config with new env vars
import importlib
if 'utils.config' in sys.modules:
    importlib.reload(sys.modules['utils.config'])

from utils.config import is_planner_llm_ready, log_config_status

async def test_e2e():
    """Test end-to-end by sending a task through WebSocket."""
    print("=" * 60)
    print("E2E TEST: Real Agent Execution")
    print("=" * 60)

    # Check configuration
    log_config_status()

    if not is_planner_llm_ready():
        print("[ERROR] LLM not configured. Please set API key in .env")
        return

    print("[OK] LLM configured")

    # Connect to WebSocket
    uri = "ws://127.0.0.1:8765/ws"
    print(f"Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as websocket:
            print("[OK] Connected to agent backend")

            # Send start run message
            task = "find wireless earbuds and add the best one to my cart"
            start_message = {
                "type": "START_RUN",
                "runId": "test-e2e-001",
                "task": task,
                "url": "http://localhost:3001",  # fake-store
            }

            print(f"Sending task: {task}")
            await websocket.send(json.dumps(start_message))

            # Listen for responses
            print("Listening for responses...")
            timeout = 60  # 60 seconds timeout
            start_time = asyncio.get_event_loop().time()

            while True:
                try:
                    message = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=5.0
                    )
                    data = json.loads(message)
                    print(f"Received: {data.get('type', 'UNKNOWN')}")

                    if data.get("type") == "RUN_COMPLETE":
                        print("[OK] Run completed successfully")
                        print(f"Final state: {data}")
                        break
                    elif data.get("type") == "RUN_ERROR":
                        print(f"[ERROR] Run failed: {data.get('error')}")
                        break
                    elif data.get("type") == "RUN_WAITING_FOR_USER":
                        print(f"[WAIT] Waiting for user: {data.get('message')}")
                        # For E2E test, we can't handle user input
                        print("[ERROR] E2E test requires user interaction - stopping")
                        break

                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed > timeout:
                        print(f"[ERROR] Timeout after {timeout}s")
                        break

                except asyncio.TimeoutError:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed > timeout:
                        print(f"[ERROR] Timeout after {timeout}s")
                        break
                    # Continue waiting

    except ConnectionRefusedError:
        print("[ERROR] Connection refused - is backend running?")
        print("Start backend with: cd agent-backend && python main.py")
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_e2e())
