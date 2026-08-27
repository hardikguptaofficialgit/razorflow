import logging
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_ROOT = Path(__file__).resolve().parent

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

load_dotenv(_REPO_ROOT / ".env")
load_dotenv(_BACKEND_ROOT / ".env", override=True)

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    uvicorn.run(
        "core.bridge_server:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
    )
