"""Local-only ETABS HTTP bridge. Run on 127.0.0.1 only; never expose publicly."""
from __future__ import annotations

import os
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from etabs_client import EtabsError, create_client

app = FastAPI(title="Element Selector ETABS Bridge", version="1.0")
_client = None


def get_client():
    global _client
    if _client is None:
        _client = create_client()
    return _client


class SelectRequest(BaseModel):
    element_ids: list[str] = Field(min_length=1, max_length=100000)
    element_type: Literal["frame", "area", "joint"] = "frame"
    clear_first: bool = False


class GroupRequest(BaseModel):
    group_name: str = Field(min_length=1, max_length=80)
    element_ids: list[str] = Field(min_length=1, max_length=100000)
    element_type: Literal["frame", "area", "joint"] = "frame"


@app.get("/health")
async def health():
    return {"ok": True, "service": "element-selector-etabs-bridge", "mock": os.getenv("MOCK", "0") == "1"}


@app.get("/status")
async def status():
    try:
        return get_client().status()
    except EtabsError as exc:
        return {"connected": False, "model_loaded": False, "model_file": "", "units": "", "etabs_version": "", "mock": os.getenv("MOCK", "0") == "1", "message": str(exc)}
    except Exception as exc:
        return {"connected": False, "model_loaded": False, "message": f"Could not connect to ETABS: {exc}"}


@app.get("/tables")
async def tables():
    try:
        client = get_client()
        return {"tables": client.list_tables(), "mock": client.mock}
    except EtabsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/table/{name:path}")
async def table(name: str):
    try:
        client = get_client()
        rows = client.get_table(name)
        return {"name": name, "rows": rows, "columns": list(rows[0].keys()) if rows else [], "mock": client.mock}
    except EtabsError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 503, detail=str(exc)) from exc


@app.post("/select")
async def select(request: SelectRequest):
    try:
        return get_client().select(request.element_ids, request.element_type, request.clear_first)
    except EtabsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/group")
async def group(request: GroupRequest):
    try:
        return get_client().save_group(request.group_name, request.element_ids, request.element_type)
    except EtabsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/refresh_view")
async def refresh_view():
    try:
        return get_client().refresh_view()
    except EtabsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
