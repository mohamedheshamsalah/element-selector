# Element Selector

A general-purpose Streamlit tool for selecting rows from CSV and Excel tables. Designed with ETABS/engineering exports in mind, but it does not assume any particular column names.

## Features

- CSV (.csv), Excel (.xlsx), and legacy Excel (.xls) uploads; delimiter/encoding detection and worksheet selection.
- Column type detection, preview, visual AND/OR conditions, text/number/date operators, and a restricted advanced query mode.
- A single-page interface with upload, conditions, matching rows, and exports together.
- Match counts, manual row selection, Excel/CSV/ID exports, and optional advanced conditions and presets.
- Session presets with JSON import/export, plus a built-in sample dataset.

## Run locally

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

Streamlit prints a local URL (usually http://localhost:8501). The app processes uploaded files in the running session; it does not save uploaded files to disk.

## Deploy free on Streamlit Community Cloud

1. Create a GitHub account if you do not already have one, then create a new repository for this project.
2. Add `app.py`, `requirements.txt`, and this `README.md` to the repository and push them to the default branch. Do not commit private engineering datasets.
3. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) with GitHub and authorize access to the repository.
4. Choose **Create app**, select the repository, branch, and `app.py` as the main file, then deploy.
5. The app is available at the Streamlit-provided `*.streamlit.app` URL. Repository changes can be redeployed from the app dashboard.

Community Cloud requires GitHub authorization. Its free hosting policies and resource limits may change; check the current Streamlit documentation for the latest terms.

## Package as a Windows executable

Streamlit apps are server processes, so a one-file EXE is best treated as a local launcher/server package. PyInstaller packaging can be fragile because Streamlit discovers package assets dynamically; test the output on a clean Windows machine.

1. On Windows, install Python and project dependencies (`python -m pip install -r requirements.txt`).
2. Install PyInstaller: `python -m pip install pyinstaller`.
3. Create `run_app.py` alongside `app.py`:

   ```python
   import sys
   from streamlit.web import cli as stcli
   sys.argv = ["streamlit", "run", "app.py", "--server.headless=true"]
   raise SystemExit(stcli.main())
   ```

4. Build a folder-based bundle first (recommended):

   ```powershell
   pyinstaller --onedir --name ElementSelector run_app.py
   ```

5. Include `app.py`, `requirements.txt`, and Streamlit's package data in the bundle. PyInstaller may need explicit `--collect-all streamlit` and package data flags depending on versions. Launch the executable, then open the local Streamlit URL printed in its console. For a polished no-console launcher, add a small desktop wrapper that starts the bundled server and opens a browser.
6. Test the packaged folder on a machine that does not have Python. Rebuild and retest after dependency updates. For a dependable installation for non-technical users, distributing a signed installer or providing a hosted Streamlit Cloud URL is usually easier than a one-file EXE.

## Filtering logic examples

`apply_conditions()` is a pure helper that can be exercised with simple assertions. In the project folder, run:

```bash
python -m unittest discover -s tests -v
```

The tests cover numeric/text filtering, AND/OR, empty values, safe advanced-query restrictions, and an unknown column. Advanced query expressions are parsed against a strict AST allowlist before pandas receives the expression; function calls, attributes, and arbitrary Python code are rejected.

## Notes

- Presets are kept in the current browser session; export a JSON preset to persist/share it.
- Selection changes affect the exports, while the on-screen display-column choice only changes the visible table.
- The clipboard list is provided as selectable text because browser clipboard writes are restricted in ordinary Streamlit sessions.
