"""PyInstaller entrypoint for the loopback-only FastAPI bridge."""
from __future__ import annotations

import os
import uvicorn

os.environ.setdefault("MOCK", "0")
uvicorn.run("bridge:app", host="127.0.0.1", port=8000, log_level="info", access_log=False)
