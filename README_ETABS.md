# Element Selector + ETABS Ultimate 20.3.0

Target confirmed from the About ETABS screenshot: **ETABS Ultimate 64-bit, Version 20.3.0 Build 2929, Windows 10 64-bit**. The packaged build instructions therefore require a 64-bit Windows build environment.

## Quick start for your friend

1. Open ETABS Ultimate 20.3.0 (64-bit), open the model, and run analysis/design if the results table you need depends on it. If ETABS has several windows, use ETABS **Set as active instance for API** for the intended model.
2. Extract the delivered `ElementSelector-Windows.zip` folder to a local folder. Keep `start.bat`, `stop.bat`, and the `ElementSelector`, `EtabsBridge`, and `DebugReport` folders together.
3. Double-click `start.bat`. It starts the local bridge, waits for its health check, starts Element Selector, and opens `http://127.0.0.1:8501`.
4. In the app sidebar choose **Connect to ETABS**, choose a table discovered from the active model, then click **Load selected table**. Add conditions and refine the matching rows. Select an ID column (the app prefers `UniqueName` when present), choose the ETABS object type, then use **Select in ETABS** or **Save as group in ETABS**.
5. Double-click `stop.bat` when finished. Try on a copy or small model before using a production project.

The app and bridge are designed to run on the same Windows PC as ETABS. The bridge binds only to `127.0.0.1`; it is not a public network service. The existing hosted upload-only app is separate and cannot connect to ETABS on a friend's PC. No table names, design result field names, design code, or element IDs are hardcoded in the real path. The app discovers the available table keys from the open model and reads that table's returned field keys.

## Connection self-test and diagnostics

In the local app sidebar choose **Check connection** and click **Run bridge, status, and table-list checks**. Then choose a live table, load it, and select the column and object type to use for the one-element test. No ID-column names are guessed. The final step changes ETABS selection, so run it only when that is acceptable.

Before trying to troubleshoot, run `DebugReport\DebugReport.exe` on the ETABS PC. It prints the ETABS version, connection result, discovered table keys, and the first five rows from a table. Alternatively, with Python installed, run `python DEBUG_REPORT.py` (or pass an exact table key as an argument). Review the output and remove confidential model/table values before sharing it. Send the exact error text or a screenshot if the connection still fails.

## Mock mode and tests

Mock mode never starts or calls ETABS. In a terminal in the project folder:

```powershell
$env:MOCK = "1"
python -m uvicorn bridge:app --host 127.0.0.1 --port 8000
```

In a second terminal, run the app with the local UI enabled:

```powershell
$env:ELEMENT_SELECTOR_LOCAL = "1"
$env:MOCK = "1"
streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

Run automated tests with:

```powershell
python -m pip install -r requirements-build.txt
python -m pytest -q
```

The mock model includes fake database tables, five representative frame/area/joint IDs, API selection failures, group assignment, and view refresh. Unit tests exercise bridge health/status/table discovery/table loading/select/group/refresh plus the existing row-filtering tests.

## Build the Windows folder application

Build on 64-bit Windows 10 with a 64-bit Python 3.11 installation. The recipient does not need Python after packaging. From PowerShell in the project directory, run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

The script builds app, bridge and debug-report folders with PyInstaller, copies launchers and documentation, and creates `ElementSelector-Windows.zip`. Build on Windows because PyInstaller does not cross-compile Windows COM applications from this Linux development environment. The app uses `comtypes` to attach to the active CSI ETABS COM object. Both ETABS and the package must be 64-bit, and process elevation must be compatible.

## Troubleshooting

- **ETABS not found / bridge says not connected:** Open ETABS and a model before starting. Check `DebugReport.exe` output. The app attaches to a running ETABS instance; it does not launch ETABS.
- **No model loaded:** Open the desired `.edb` model in ETABS, make it the active API instance, then refresh/restart the app.
- **32/64-bit mismatch:** This target is ETABS 20.3.0 64-bit. Build with 64-bit Python and run the resulting 64-bit package.
- **ETABS and app have different privilege levels:** Run both normally, or run both at the same Windows privilege level. Do not elevate only one.
- **Several ETABS windows:** In ETABS use **Set as active instance for API** on the intended model, then restart `start.bat`.
- **Table not found / empty results:** Table keys are read from the current model and are not fixed in code. Choose a listed table. Some analysis/design tables are empty until the relevant analysis or design has run.
- **Selection not visible:** Confirm the ID column maps to an ETABS object name in the selected object type. `UniqueName` is preferred only when that field is present; other models may require choosing another available ID field. Confirm the object is in the active model and inspect failed names shown by the app.
- **Group or selection API error:** Copy the complete message. API return codes are checked and surfaced, but only a real ETABS run can confirm version-specific behavior and ID-field mapping.
- **Antivirus blocks an executable:** The bundle is unsigned. Follow your organization's software policy, scan the files, and ask IT to allow a verified build rather than disabling protection.
- **Bridge health check times out:** Close the app with `stop.bat`, verify port 8000/8501 is not occupied, then retry. Do not expose or forward the bridge ports to the internet.

## Verification status

**Verified in MOCK mode in this development environment:** Python syntax checks; all unit tests for filtering and bridge API contract; fake status, table listing/loading, select behavior and failed IDs, group save, refresh, and request validation. MOCK tests do not launch ETABS and do not modify a real model.

**Not yet verified on real ETABS Ultimate 20.3.0 Build 2929:** COM activation/bitness/elevation, CSI v20.3 comtypes generated signatures and tuple layouts, active instance behavior, live table availability/row parsing, mapping a selected table ID field to FrameObj/AreaObj/PointObj names, clear-first selection, visible UI refresh, and group creation. These need the Windows 10/ETABS installation shown in the screenshot and a small test model. Design code was not provided and is not assumed by the generic dynamic-table workflow.

## API references

CSI states its APIs support Python and that ETABS v18+ APIs are forward-compatible to future major versions; the precise calls still require validation against the installed version: [CSI Developer](https://www.csiamerica.com/developer). The bridge uses CSI's documented selection/clear-selection methods: [FrameObj.SetSelected](https://docs.csiamerica.com/help-files/etabs-api-2016/html/5fc99827-8828-6c25-4b0a-c1c3e95fb2e3.htm), [PointObj.SetSelected](https://docs.csiamerica.com/help-files/etabs-api-2016/html/9d2e643a-f7cc-bb04-115d-5a4ce22e39e5.htm), [SelectObj.ClearSelection](https://docs.csiamerica.com/help-files/etabs-api-2016/html/bbac56bd-c6f3-8f22-3b8b-bdd8c6f6b814.htm), and [FrameObj.SetGroupAssign](https://docs.csiamerica.com/help-files/etabs-api-2016/html/22d7de81-6fdd-b047-7d6d-8f3b6ced239a.htm). CSI documents zero as successful return for these APIs.
