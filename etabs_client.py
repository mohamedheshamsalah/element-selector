"""The only module that calls the CSI ETABS COM API.

The real branch is intentionally isolated and is NOT validated against ETABS in this
Linux build environment. Table names and field names are discovered from the active model.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class EtabsError(RuntimeError):
    """Readable failure raised for ETABS/API problems."""


def _check_ret(ret: Any, action: str) -> None:
    """CSI API methods generally return 0 on success; reject other codes clearly."""
    try:
        code = int(ret)
    except (TypeError, ValueError):
        raise EtabsError(f"{action} returned an unexpected status: {ret!r}")
    if code != 0:
        raise EtabsError(f"ETABS API call '{action}' failed with return code {code}.")


class MockEtabsClient:
    """Realistic fake ETABS model used for development and automated tests."""
    mock = True
    SAMPLE_TABLES = {
        "Frame Design Ratios - AISC 360-16": [
            {"UniqueName": "F101", "Story": "Roof", "Label": "101", "Section": "W14X90", "DCRatio": 0.72, "ObjectType": "frame"},
            {"UniqueName": "F102", "Story": "Roof", "Label": "102", "Section": "W14X90", "DCRatio": 1.08, "ObjectType": "frame"},
            {"UniqueName": "F201", "Story": "Story 3", "Label": "201", "Section": "W18X35", "DCRatio": 0.91, "ObjectType": "frame"},
            {"UniqueName": "A301", "Story": "Story 2", "Label": "301", "Section": "SLAB-200", "DCRatio": 0.64, "ObjectType": "area"},
            {"UniqueName": "J401", "Story": "Story 1", "Label": "401", "Section": "Joint", "DCRatio": 0.00, "ObjectType": "joint"},
        ],
        "Joint Reactions": [
            {"UniqueName": "J401", "Story": "Story 1", "Label": "401", "Section": "Joint", "DCRatio": 0.0, "ObjectType": "joint"},
        ],
    }

    def __init__(self) -> None:
        self.selection: dict[str, set[str]] = {"frame": set(), "area": set(), "joint": set()}
        self.groups: dict[str, dict[str, set[str]]] = {}
        self.refreshed = False

    def status(self) -> dict[str, Any]:
        return {"connected": True, "model_loaded": True, "model_file": "MOCK_Building.edb", "units": "kN, m, C", "etabs_version": "MOCK ETABS Ultimate 20.3.0 Build 2929", "mock": True}

    def list_tables(self) -> list[str]:
        return list(self.SAMPLE_TABLES)

    def get_table(self, name: str) -> list[dict[str, Any]]:
        if name not in self.SAMPLE_TABLES:
            raise EtabsError(f"Table not found in the mock model: {name}")
        return [dict(row) for row in self.SAMPLE_TABLES[name]]

    def select(self, element_ids: list[str], element_type: str = "frame", clear_first: bool = False) -> dict[str, Any]:
        kind = _normalize_kind(element_type)
        if clear_first:
            for values in self.selection.values():
                values.clear()
        valid = {str(row["UniqueName"]) for rows in self.SAMPLE_TABLES.values() for row in rows if row["ObjectType"] == kind}
        selected = [str(name) for name in element_ids if str(name) in valid]
        failed = [str(name) for name in element_ids if str(name) not in valid]
        self.selection[kind].update(selected)
        return {"selected_count": len(selected), "failed_names": failed, "mock": True}

    def save_group(self, group_name: str, element_ids: list[str], element_type: str = "frame") -> dict[str, Any]:
        name = _validate_group_name(group_name)
        kind = _normalize_kind(element_type)
        self.groups.setdefault(name, {"frame": set(), "area": set(), "joint": set()})[kind].update(map(str, element_ids))
        return {"group_name": name, "assigned_count": len(element_ids), "failed_names": [], "mock": True}

    def refresh_view(self) -> dict[str, Any]:
        self.refreshed = True
        return {"refreshed": True, "mock": True}


def _normalize_kind(element_type: str) -> str:
    value = str(element_type).strip().lower()
    if value not in {"frame", "area", "joint"}:
        raise EtabsError("element_type must be frame, area, or joint.")
    return value


def _validate_group_name(group_name: str) -> str:
    name = str(group_name).strip()
    if not name or len(name) > 80:
        raise EtabsError("Group name must contain 1–80 non-space characters.")
    return name


def parse_table_response(table_name: str, result: Any) -> list[dict[str, Any]]:
    """Parse the CSI COM ref/out tuple: FieldKeyList, version, fields, rows, flat data, ret."""
    if not isinstance(result, tuple) or len(result) < 6:
        raise EtabsError(f"GetTableForDisplayArray returned an unexpected response: {result!r}")
    _check_ret(result[-1], "DatabaseTables.GetTableForDisplayArray")
    field_keys = [str(v) for v in (result[2] or [])]
    record_count = int(result[3])
    flat = list(result[4] or [])
    if not field_keys:
        return []
    width = len(field_keys)
    if len(flat) != record_count * width:
        raise EtabsError(f"Table '{table_name}' reported {record_count} rows x {width} columns but returned {len(flat)} values.")
    return [dict(zip(field_keys, flat[i:i + width])) for i in range(0, len(flat), width)]


class RealEtabsClient:
    """Thin adapter around the active ETABS COM object; all COM operations live here."""
    mock = False
    PROG_ID = "CSI.ETABS.API.ETABSObject"

    def __init__(self) -> None:
        if os.name != "nt":
            raise EtabsError("Real ETABS connection is available only on Windows. Run MOCK=1 outside Windows.")
        try:
            import comtypes.client
            self._comtypes = comtypes.client
            self.etabs = comtypes.client.GetActiveObject(self.PROG_ID)
            self.sap = self.etabs.SapModel
        except Exception as exc:
            raise EtabsError("Could not attach to running ETABS. Open ETABS and a model, then set this instance as active for the API. Details: " + str(exc)) from exc
        if self.sap is None:
            raise EtabsError("ETABS is open, but no model is loaded.")

    @staticmethod
    def _last_return_code(result: Any, action: str) -> None:
        if isinstance(result, tuple):
            if not result:
                raise EtabsError(f"{action} returned an empty API response.")
            _check_ret(result[-1], action)
        else:
            _check_ret(result, action)

    def status(self) -> dict[str, Any]:
        try:
            model_file = str(self.sap.GetModelFilename())
            units = str(self.sap.GetPresentUnits())
            version_result = self.sap.GetVersion()
            if isinstance(version_result, tuple):
                version = str(version_result[0])
                self._last_return_code(version_result, "SapModel.GetVersion")
            else:
                version = str(version_result)
            return {"connected": True, "model_loaded": bool(model_file), "model_file": Path(model_file).name if model_file else "", "units": units, "etabs_version": version, "mock": False}
        except EtabsError:
            raise
        except Exception as exc:
            raise EtabsError(f"Could not read ETABS status: {exc}") from exc

    def list_tables(self) -> list[str]:
        try:
            result = self.sap.DatabaseTables.GetAvailableTables()
            if not isinstance(result, tuple) or len(result) < 4:
                raise EtabsError(f"GetAvailableTables returned an unexpected response: {result!r}")
            self._last_return_code(result, "DatabaseTables.GetAvailableTables")
            # GetAvailableTables returns NumberTables, TableKey[], TableName[], ImportType[], ret.
            # GetTableForDisplayArray accepts TableKey, so expose the discovered table keys.
            table_keys = result[1]
            if table_keys is None:
                raise EtabsError("ETABS returned no table keys. Ensure the model is loaded.")
            return [str(key) for key in table_keys]
        except EtabsError:
            raise
        except Exception as exc:
            raise EtabsError(f"Could not list ETABS tables: {exc}") from exc

    def get_table(self, name: str) -> list[dict[str, Any]]:
        if name not in self.list_tables():
            raise EtabsError(f"Table not found in the active model: {name}")
        try:
            result = self.sap.DatabaseTables.GetTableForDisplayArray(name, [], "", 0, [], 0, [])
            return parse_table_response(name, result)
        except EtabsError:
            raise
        except Exception as exc:
            raise EtabsError(f"Could not read ETABS table '{name}': {exc}") from exc

    def select(self, element_ids: list[str], element_type: str = "frame", clear_first: bool = False) -> dict[str, Any]:
        kind = _normalize_kind(element_type)
        api_name = {"frame": "FrameObj", "area": "AreaObj", "joint": "PointObj"}[kind]
        try:
            if clear_first:
                self._last_return_code(self.sap.SelectObj.ClearSelection(), "SelectObj.ClearSelection")
            failed = []
            api = getattr(self.sap, api_name)
            for element_id in map(str, element_ids):
                result = api.SetSelected(element_id, True)
                if isinstance(result, tuple):
                    result = result[-1]
                if int(result) != 0:
                    failed.append(element_id)
            return {"selected_count": len(element_ids) - len(failed), "failed_names": failed, "mock": False}
        except EtabsError:
            raise
        except Exception as exc:
            raise EtabsError(f"Failed to select {kind} objects: {exc}") from exc

    def save_group(self, group_name: str, element_ids: list[str], element_type: str = "frame") -> dict[str, Any]:
        name = _validate_group_name(group_name)
        kind = _normalize_kind(element_type)
        api_name = {"frame": "FrameObj", "area": "AreaObj", "joint": "PointObj"}[kind]
        try:
            self._last_return_code(self.sap.GroupDef.SetGroup(name), "GroupDef.SetGroup")
            api = getattr(self.sap, api_name)
            failed = []
            for element_id in map(str, element_ids):
                result = api.SetGroupAssign(element_id, name)
                if isinstance(result, tuple):
                    result = result[-1]
                if int(result) != 0:
                    failed.append(element_id)
            return {"group_name": name, "assigned_count": len(element_ids) - len(failed), "failed_names": failed, "mock": False}
        except EtabsError:
            raise
        except Exception as exc:
            raise EtabsError(f"Failed to create or assign ETABS group '{name}': {exc}") from exc

    def refresh_view(self) -> dict[str, Any]:
        try:
            result = self.sap.View.RefreshView(0, False)
            if isinstance(result, tuple):
                result = result[-1]
            _check_ret(result, "View.RefreshView")
            return {"refreshed": True, "mock": False}
        except EtabsError:
            raise
        except Exception as exc:
            raise EtabsError(f"Could not refresh the ETABS view: {exc}") from exc


def create_client() -> MockEtabsClient | RealEtabsClient:
    """Use MOCK=1 to get deterministic fake data; otherwise connect to ETABS."""
    if os.getenv("MOCK", "0").strip() == "1":
        return MockEtabsClient()
    return RealEtabsClient()
