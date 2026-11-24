"""PyInstaller entrypoint for the local Streamlit UI."""
from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    base_dir = Path(__file__).resolve().parent

os.environ["ELEMENT_SELECTOR_LOCAL"] = "1"
os.environ.setdefault("MOCK", "0")
app_path = base_dir / "app.py"
if not app_path.exists():
    raise SystemExit(f"Element Selector app.py was not bundled. Expected: {app_path}")

from streamlit.web import cli as stcli  # noqa: E402

sys.argv = ["streamlit", "run", str(app_path), "--server.address=127.0.0.1", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
raise SystemExit(stcli.main())
