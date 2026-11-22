from __future__ import annotations

import ast
import csv
import io
import json
import re
from datetime import date, datetime
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Element Selector", page_icon="⌖", layout="wide", initial_sidebar_state="collapsed")

# ---------- Visual system ----------
st.markdown("""
<style>
:root { color-scheme: light; --ink:#202b36; --muted:#667482; --line:#dce3e8; --paper:#ffffff; --accent:#416b86; --soft:#f5f8fa; }
html, body, [class*="css"] { font-family:Arial,Helvetica,sans-serif; }
.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { background:#ffffff !important; color:var(--ink) !important; }
[data-testid="stSidebar"] { display:none !important; }
h1,h2,h3,p,label,span { color:var(--ink); }
[data-testid="stCaptionContainer"] p { color:var(--muted) !important; }
div[data-testid="stMetric"] { background:#ffffff; border:1px solid var(--line); padding:.8rem 1rem; border-radius:6px; box-shadow:none !important; }
.stButton>button[kind="primary"] { background:var(--accent); border-color:var(--accent); color:#ffffff; }
.stButton>button { border-radius:5px; box-shadow:none !important; }
[data-testid="stFileUploader"] { background:var(--soft); border:1px solid var(--line); border-radius:6px; box-shadow:none !important; }
hr { border-color:var(--line); }
[data-testid="stDataFrame"], [data-testid="stDataEditor"] { border:1px solid var(--line); border-radius:6px; overflow:hidden; box-shadow:none !important; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-color:var(--line) !important; border-radius:6px; box-shadow:none !important; }
input, textarea, [data-baseweb="select"] > div { background:#ffffff !important; color:var(--ink) !important; border-color:var(--line) !important; }
</style>
""", unsafe_allow_html=True)

SAMPLE_ROWS = [
    ("C101","Roof","Column","W14x90",0.72,-420,38,21),("C102","Roof","Column","W14x90",1.08,-510,52,30),
    ("B201","Story 3","Beam","W18x35",0.64,-85,16,42),("B202","Story 3","Beam","W18x35",0.91,-103,22,51),
    ("C201","Story 3","Column","W14x90",0.88,-630,61,39),("C202","Story 3","Column","W14x90",1.24,-720,74,45),
    ("B301","Story 2","Beam","W21x44",0.55,-124,19,64),("B302","Story 2","Beam","W21x44",0.96,-142,24,72),
    ("C301","Story 2","Column","W14x99",0.68,-840,83,54),("C302","Story 2","Column","W14x99",1.12,-930,91,60),
    ("B401","Story 1","Beam","W24x55",0.81,-176,31,88),("B402","Story 1","Beam","W24x55",1.36,-195,35,96),
    ("C401","Story 1","Column","W14x120",0.93,-1150,118,78),("C402","Story 1","Column","W14x120",0.77,-1280,126,84),
    ("B501","Base","Beam","W24x55",0.43,-210,37,102),("C501","Base","Column","W14x120",0.98,-1480,142,92),
]

@st.cache_data(show_spinner=False)
def read_uploaded_file(data: bytes, filename: str, sheet_name: str | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Read CSV or Excel bytes with basic encoding/delimiter detection."""
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix == "csv":
        text = None
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("This CSV encoding could not be read. Please save the file as UTF-8 and try again.")
        try:
            dialect = csv.Sniffer().sniff(text[:65536], delimiters=",\t;|")
            sep = dialect.delimiter
        except csv.Error:
            sep = ","
        frame = pd.read_csv(io.StringIO(text), sep=sep, engine="python")
        return frame, ["CSV"]
    if suffix in {"xlsx", "xls"}:
        engine = "openpyxl" if suffix == "xlsx" else "xlrd"
        try:
            book = pd.ExcelFile(io.BytesIO(data), engine=engine)
            selected = sheet_name if sheet_name in book.sheet_names else book.sheet_names[0]
            frame = pd.read_excel(book, sheet_name=selected)
            return frame, book.sheet_names
        except ImportError as exc:
            raise ValueError("Excel reader dependency is missing. Install the packages in requirements.txt.") from exc
    raise ValueError("Unsupported file type. Upload a .csv, .xlsx, or .xls file.")


def detect_type(series: pd.Series) -> str:
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    if pd.api.types.is_numeric_dtype(series):
        return "number"
    nonempty = series.dropna()
    if len(nonempty) and (pd.to_datetime(nonempty, errors="coerce").notna().mean() >= .9):
        return "date"
    return "text"


def parse_value(value: Any, kind: str) -> Any:
    if kind == "number":
        return float(value)
    if kind == "date":
        return pd.to_datetime(value)
    return str(value)


def apply_conditions(df: pd.DataFrame, conditions: list[dict[str, Any]], combine: str = "AND") -> pd.DataFrame:
    """Return rows satisfying the visual conditions. Exposed separately for unit tests."""
    if not conditions:
        return df.copy()
    masks: list[pd.Series] = []
    for rule in conditions:
        col, op = rule["column"], rule["operator"]
        if col not in df.columns:
            raise ValueError(f"Column not found: {col}")
        s = df[col]
        kind = detect_type(s)
        if op == "is empty":
            mask = s.isna() | s.astype("string").str.strip().eq("")
        elif op == "is not empty":
            mask = s.notna() & ~s.astype("string").str.strip().eq("")
        elif op == "between":
            lo, hi = rule["value"]
            mask = pd.to_numeric(s, errors="coerce").between(float(lo), float(hi), inclusive="both")
        elif kind == "number":
            left = pd.to_numeric(s, errors="coerce")
            right = float(rule["value"])
            mask = {">": left.gt, ">=": left.ge, "<": left.lt, "<=": left.le, "=": left.eq, "!=": left.ne}[op](right)
        elif kind == "date":
            left = pd.to_datetime(s, errors="coerce")
            right = pd.to_datetime(rule["value"])
            mask = {">": left.gt, ">=": left.ge, "<": left.lt, "<=": left.le, "=": left.eq, "!=": left.ne}[op](right)
        else:
            left = s.astype("string").fillna("").str.casefold()
            value = str(rule["value"]).casefold()
            if op == "equals": mask = left.eq(value)
            elif op == "not equals": mask = left.ne(value)
            elif op == "contains": mask = left.str.contains(value, regex=False, na=False)
            elif op == "starts with": mask = left.str.startswith(value, na=False)
            elif op == "ends with": mask = left.str.endswith(value, na=False)
            elif op == "is one of": mask = left.isin([str(v).casefold() for v in rule["value"]])
            else: raise ValueError(f"Unsupported text operator: {op}")
        masks.append(pd.Series(mask, index=df.index).fillna(False))
    combined = masks[0]
    for mask in masks[1:]:
        combined = (combined & mask) if combine.upper() == "AND" else (combined | mask)
    return df.loc[combined].copy()

_ALLOWED_AST = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.Compare,
                ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
                ast.Name, ast.Load, ast.Constant, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
                ast.Mod, ast.USub, ast.UAdd, ast.BitAnd, ast.BitOr, ast.Invert)

def validate_query(expression: str, columns: list[str]) -> None:
    """Whitelist a restricted pandas-query expression before passing it to DataFrame.query."""
    if len(expression) > 500:
        raise ValueError("Keep advanced conditions under 500 characters.")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Check the condition syntax. Example: dc_ratio > 1 and type == 'Column'.") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_AST):
            raise ValueError("For safety, advanced conditions support only column names, values, comparisons, and AND/OR — no function calls or Python code.")
        if isinstance(node, ast.Name) and node.id not in columns:
            raise ValueError(f"Unknown column '{node.id}'. Use the exact column name, or wrap names with spaces in backticks.")


def apply_advanced_query(df: pd.DataFrame, expression: str) -> pd.DataFrame:
    if not expression.strip():
        return df.copy()
    aliases: dict[str, str] = {}
    rewritten = expression
    for i, name in enumerate(re.findall(r"`([^`]+)`", expression)):
        if name not in df.columns:
            raise ValueError(f"Unknown column '{name}'. Choose a column from the uploaded table.")
        alias = f"__column_{i}"
        aliases[alias] = name
        rewritten = rewritten.replace(f"`{name}`", alias)
    validate_query(rewritten, [*map(str, df.columns), *aliases.keys()])
    try:
        query_frame = df.rename(columns={name: alias for alias, name in aliases.items()}) if aliases else df
        return query_frame.query(rewritten, engine="python").rename(columns={alias: name for alias, name in aliases.items()}).copy()
    except Exception as exc:
        raise ValueError(f"Could not apply that condition: {exc}") from exc


def to_excel_bytes(frame: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Selected elements")
    return output.getvalue()


def sample_data() -> pd.DataFrame:
    return pd.DataFrame(SAMPLE_ROWS, columns=["element", "story", "type", "section", "dc_ratio", "P", "M3", "V2"])


def render_rule(index: int, df: pd.DataFrame) -> dict[str, Any] | None:
    cols = [str(c) for c in df.columns]
    with st.container(border=True):
        st.markdown(f"**Condition {index + 1}**")
        left, middle, right = st.columns([1.4, 1.3, .35])
        column = left.selectbox("Column", cols, key=f"c_{index}")
        kind = detect_type(df[column])
        if kind == "number":
            ops = [">", ">=", "<", "<=", "=", "!=", "between", "is empty", "is not empty"]
        elif kind == "date":
            ops = [">", ">=", "<", "<=", "=", "!=", "is empty", "is not empty"]
        else:
            ops = ["equals", "not equals", "contains", "starts with", "ends with", "is one of", "is empty", "is not empty"]
        operator = middle.selectbox("Operator", ops, key=f"o_{index}")
        if right.button("Remove", key=f"remove_{index}", help="Remove this condition"):
            st.session_state.rules.pop(index)
            st.rerun()
        if operator in ("is empty", "is not empty"):
            value = None
        elif operator == "between":
            v1, v2 = st.columns(2)
            value = (v1.number_input("Minimum", value=float(pd.to_numeric(df[column], errors="coerce").min() or 0), key=f"v1_{index}"),
                     v2.number_input("Maximum", value=float(pd.to_numeric(df[column], errors="coerce").max() or 1), key=f"v2_{index}"))
        elif operator == "is one of":
            opts = sorted(df[column].dropna().astype(str).unique().tolist())
            value = st.multiselect("Values", opts, key=f"v_{index}")
        elif kind == "number":
            numeric = pd.to_numeric(df[column], errors="coerce").dropna()
            default = float(numeric.median()) if not numeric.empty else 0.0
            value = st.number_input("Value", value=default, key=f"v_{index}")
        elif kind == "date":
            dt = pd.to_datetime(df[column], errors="coerce").dropna()
            default = dt.iloc[0].date() if len(dt) else date.today()
            value = st.date_input("Date", value=default, key=f"v_{index}")
        else:
            unique = df[column].dropna().astype(str).unique().tolist()
            if len(unique) <= 20 and operator in ("equals", "not equals"):
                value = st.selectbox("Value", unique or [""], key=f"v_{index}")
            else:
                value = st.text_input("Value", key=f"v_{index}")
        return {"column": column, "operator": operator, "value": value}


def main() -> None:
    """Single-page flow: load data, add filters, and review matching rows."""
    defaults = {
        "rules": [], "data": None, "selected_indices": set(),
        "presets": {}, "active_name": "",
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

    st.title("Element Selector")
    st.caption("Filter a table and export the matching rows.")

    upload_col, sample_col = st.columns([3, 1])
    uploaded = upload_col.file_uploader("Data file", type=["csv", "xlsx", "xls"], label_visibility="collapsed")
    if sample_col.button("Use sample data", use_container_width=True):
        st.session_state.data = sample_data()
        st.session_state.source_name = "Built-in sample"
        st.session_state.selected_indices = set(st.session_state.data.index)
        st.session_state.rules = []
        st.session_state.pop("advanced_expression", None)
        st.session_state.pop("advanced_result", None)
        st.rerun()

    if uploaded is not None:
        try:
            raw = uploaded.getvalue()
            sheet = None
            if uploaded.name.lower().endswith((".xlsx", ".xls")):
                _, sheet_names = read_uploaded_file(raw, uploaded.name)
                if len(sheet_names) > 1:
                    sheet = st.selectbox("Sheet", sheet_names, key=f"sheet_{uploaded.name}")
                else:
                    sheet = sheet_names[0]
            frame, _ = read_uploaded_file(raw, uploaded.name, sheet)
            source = f"{uploaded.name} · {sheet}" if sheet else uploaded.name
            if st.session_state.get("source_name") != source or st.session_state.get("data") is None:
                st.session_state.selected_indices = set(frame.index)
                st.session_state.rules = []
                st.session_state.pop("advanced_expression", None)
                st.session_state.pop("advanced_result", None)
            st.session_state.data = frame
            st.session_state.source_name = source
        except Exception as exc:
            st.error(str(exc))

    df = st.session_state.data
    if df is None:
        st.info("Upload a CSV or Excel file, or use the sample data.")
        return
    if df.empty:
        st.warning("The file has no data rows.")
        return

    meta1, meta2, meta3 = st.columns([1, 1, 3])
    meta1.metric("Rows", f"{len(df):,}")
    meta2.metric("Columns", f"{len(df.columns):,}")
    meta3.markdown(f"**File:** {st.session_state.get('source_name', 'Data')}")

    with st.container(border=True):
        st.subheader(f"Conditions ({len(st.session_state.rules)})")
        if len(st.session_state.rules) > 1:
            st.radio(
                "Combine conditions", ["AND", "OR"], horizontal=True, key="combine",
            )
            st.caption("AND = all conditions. OR = any condition.")
        for i in range(len(st.session_state.rules)):
            rule = render_rule(i, df)
            if rule:
                st.session_state.rules[i] = rule
        add_col, clear_col, _ = st.columns([1.2, 1.2, 4])
        add_label = "＋ Add another condition" if st.session_state.rules else "＋ Add condition"
        if add_col.button(add_label, type="primary", use_container_width=True):
            st.session_state.rules.append({})
            st.rerun()
        if st.session_state.rules and clear_col.button("Clear", use_container_width=True):
            st.session_state.rules = []
            st.session_state.pop("advanced_expression", None)
            st.session_state.pop("advanced_result", None)
            st.rerun()

    with st.expander("Advanced condition or saved presets", expanded=False):
        advanced = st.toggle("Use advanced expression", key="singlepage_advanced")
        if advanced:
            expression = st.text_input("Condition", placeholder="dc_ratio > 1 and type == 'Column'")
            if st.button("Apply expression"):
                try:
                    result = apply_advanced_query(df, expression)
                    st.session_state.advanced_expression = expression
                    st.session_state.advanced_result = result
                    st.session_state.selected_indices = set(result.index)
                    st.success("Condition applied.")
                except ValueError as exc:
                    st.error(str(exc))
        else:
            st.session_state.pop("advanced_expression", None)
            st.session_state.pop("advanced_result", None)
        preset_name = st.text_input("Preset name", placeholder="Optional")
        p1, p2 = st.columns(2)
        if p1.button("Save preset"):
            if preset_name.strip():
                st.session_state.presets[preset_name.strip()] = {
                    "combine": st.session_state.get("combine", "AND"),
                    "conditions": st.session_state.rules,
                }
                st.success("Preset saved for this session.")
            else:
                st.warning("Enter a name first.")
        if st.session_state.presets:
            preset_choice = p2.selectbox("Load preset", list(st.session_state.presets), key="singlepage_load_preset")
            if p2.button("Load", key="singlepage_load_button"):
                preset = st.session_state.presets[preset_choice]
                st.session_state.rules = preset["conditions"]
                st.session_state.combine = preset.get("combine", "AND")
                st.rerun()
        import_file = st.file_uploader("Import preset JSON", type=["json"], key="singlepage_preset_import")
        if import_file is not None:
            try:
                preset = json.loads(import_file.getvalue().decode("utf-8"))
                st.session_state.rules = preset["conditions"]
                st.session_state.combine = preset.get("combine", "AND")
                st.success("Preset loaded.")
            except Exception as exc:
                st.error(f"Could not read preset: {exc}")
        if preset_name.strip() in st.session_state.presets:
            payload = json.dumps(st.session_state.presets[preset_name.strip()], indent=2, default=str)
            st.download_button("Export preset JSON", payload, file_name="conditions.json", mime="application/json")

    try:
        if st.session_state.get("advanced_expression") and st.session_state.get("advanced_result") is not None:
            matched = st.session_state.advanced_result
        else:
            matched = apply_conditions(df, st.session_state.rules, st.session_state.get("combine", "AND"))
    except Exception as exc:
        st.error(str(exc))
        matched = df.iloc[0:0].copy()

    percent = 100 * len(matched) / len(df) if len(df) else 0
    st.subheader(f"Matching rows · {len(matched):,} of {len(df):,} ({percent:.1f}%)")
    if matched.empty:
        st.info("No rows match. Adjust the conditions above.")
        return

    editable = matched.copy()
    editable.insert(0, "Select", [idx in st.session_state.selected_indices for idx in editable.index])
    edited = st.data_editor(
        editable, use_container_width=True, hide_index=True,
        disabled=[col for col in editable.columns if col != "Select"],
        column_config={"Select": st.column_config.CheckboxColumn("Select", default=True)},
        key="singlepage_result_editor",
    )
    selected_idx = {
        idx for idx, selected in zip(matched.index, edited["Select"].fillna(False).tolist()) if selected
    }
    st.session_state.selected_indices = (st.session_state.selected_indices - set(matched.index)) | selected_idx
    chosen_rows = matched.loc[matched.index.isin(selected_idx)].copy()
    st.caption(f"Selected: {len(chosen_rows):,}")

    with st.expander("Export selected rows"):
        id_column = st.selectbox("ID column (optional)", ["— none —"] + [str(c) for c in df.columns])
        ex1, ex2 = st.columns(2)
        ex1.download_button(
            "Excel", to_excel_bytes(chosen_rows), file_name="selected_elements.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=chosen_rows.empty, use_container_width=True,
        )
        ex2.download_button(
            "CSV", chosen_rows.to_csv(index=False).encode("utf-8-sig"),
            file_name="selected_elements.csv", mime="text/csv",
            disabled=chosen_rows.empty, use_container_width=True,
        )
        if id_column != "— none —":
            ids = chosen_rows[id_column].dropna().astype(str).tolist()
            st.text_area("IDs", ", ".join(ids), height=70)
            st.download_button("Download IDs", "\n".join(ids), file_name="selected_ids.txt", mime="text/plain")


if __name__ == "__main__":
    main()
