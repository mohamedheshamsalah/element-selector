# Mock-mode verification results

Run in the project directory:

```bash
MOCK=1 python -m pytest -q
```

Result on 2026-11-24:

```text
18 passed
```

The test run covered all existing filtering tests, mock bridge health/status/table listing and row loading, element selection including failed IDs, group save, view refresh, request validation, and parsing a representative flat CSI-style response tuple with return-code checking. A Streamlit AppTest also confirmed the app starts in local MOCK mode and loads the five-row fake ETABS table without app exceptions.

## Verified here

- Python syntax compilation for the app, bridge/client modules, launcher/diagnostics, and test files.
- The bridge endpoint contract against `MockEtabsClient`.
- CSV/Excel filter behavior and regression coverage from the existing app.
- Streamlit UI startup and ETABS mock table load through the HTTP bridge.
- Table response parsing with a synthetic six-item COM-style return tuple.

## Not verified here

- ETABS Ultimate 20.3.0 Build 2929 COM attachment, generated typelib behavior, actual response tuple values/ordering, table access from a real `.edb`, and API selection/group/refresh calls.
- PyInstaller Windows output, antivirus handling, and launch/stop scripts on Windows.
- Real model ID column mapping to the ETABS frame/area/joint object names. The user must test with a small model and review `DEBUG_REPORT.py` output.

The Linux sandbox cannot run ETABS or produce a validated Windows `.exe`; `build_windows.ps1` must be run and smoke-tested on Windows 10 64-bit with 64-bit Python 3.11 and ETABS Ultimate 20.3.0 Build 2929.
