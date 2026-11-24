"""HTTP client for the loopback bridge used by the local packaged app."""
from __future__ import annotations

from urllib.parse import quote

import pandas as pd
import requests

BRIDGE_URL = "http://127.0.0.1:8000"
TIMEOUT = 20


class BridgeError(RuntimeError):
    pass


def _request(method: str, path: str, **kwargs):
    try:
        response = requests.request(method, BRIDGE_URL + path, timeout=TIMEOUT, **kwargs)
    except requests.ConnectionError as exc:
        raise BridgeError("The ETABS bridge is not running. Close the app and start it again with start.bat.") from exc
    except requests.RequestException as exc:
        raise BridgeError(f"Could not reach the local ETABS bridge: {exc}") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise BridgeError(f"The bridge returned an invalid response (HTTP {response.status_code}).") from exc
    if not response.ok:
        raise BridgeError(payload.get("detail", f"Bridge request failed (HTTP {response.status_code})."))
    return payload


def health() -> dict:
    return _request("GET", "/health")


def status() -> dict:
    return _request("GET", "/status")


def list_tables() -> list[str]:
    return _request("GET", "/tables")["tables"]


def load_table(name: str) -> pd.DataFrame:
    payload = _request("GET", "/table/" + quote(name, safe=""))
    return pd.DataFrame(payload["rows"], columns=payload.get("columns") or None)


def select_elements(element_ids: list[str], element_type: str, clear_first: bool = False) -> dict:
    return _request("POST", "/select", json={"element_ids": element_ids, "element_type": element_type, "clear_first": clear_first})


def save_group(group_name: str, element_ids: list[str], element_type: str) -> dict:
    return _request("POST", "/group", json={"group_name": group_name, "element_ids": element_ids, "element_type": element_type})


def refresh_view() -> dict:
    return _request("POST", "/refresh_view")
