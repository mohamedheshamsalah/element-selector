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

st.set_page_config(page_title="Element Selector", page_icon="⌖", layout="wide", initial_sidebar_state="expanded")

# ---------- Visual system ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
:root { --ink:#182a3a; --muted:#718296; --line:#e4ebf1; --paper:#f5f8fb; --accent:#167d8d; --accent2:#dff2f1; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
.stApp { background:linear-gradient(135deg,#f7fafc 0%,#f0f6f8 100%); color:var(--ink); }
[data-testid="stSidebar"] { background:#fff; border-right:1px solid var(--line); }
[data-testid="stSidebar"] > div:first-child { padding-top:1.4rem; }
h1,h2,h3 { font-family:'Manrope',sans-serif !important; color:var(--ink); letter-spacing:-.035em; }
.hero { padding:1.45rem 1.65rem; background:linear-gradient(115deg,#123b4b,#167d8d 70%,#31a6a2); color:white; border-radius:20px; margin:0 0 1.25rem; box-shadow:0 14px 34px #123b4b1c; }
.hero h1 { color:#fff !important; margin:0; font-size:2rem; }
.hero p { margin:.4rem 0 0; color:#e0f3f4; font-size:.98rem; }
.kicker { text-transform:uppercase; letter-spacing:.16em; font-size:.69rem; font-weight:700; color:#b9e8e7; margin-bottom:.55rem; }
.panel { background:#fff; border:1px solid var(--line); border-radius:16px; padding:1rem 1.1rem; box-shadow:0 4px 16px #23394b08; }
.small-muted { color:var(--muted); font-size:.88rem; }
.step { display:inline-flex; align-items:center; justify-content:center; border-radius:50%; background:var(--accent2); color:var(--accent); font-weight:700; width:1.8rem;height:1.8rem;margin-right:.5rem; }
div[data-testid="stMetric"] { background:#fff; border:1px solid var(--line); padding:1rem 1.1rem; border-radius:15px; }
.stButton>button[kind="primary"] { background:#167d8d; border-color:#167d8d; }
hr { border-color:var(--line); }
[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:12px; overflow:hidden; }
@media (prefers-color-scheme: dark) { .stApp { background:#101a22; } .panel, div[data-testid="stMetric"] { background:#17252f; border-color:#2a3d4b; } h1,h2,h3 { color:#e4eef3; } }
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
    """Simple two-tab workflow: inspect data, then filter and export."""
    for key, default in {
        "rules": [], "data": None, "selected_indices": set(),
        "presets": {}, "active_name": "",
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

    st.sidebar.markdown("### ⌖ Element Selector")
    st.sidebar.caption("Upload a table, then choose the rows you need.")
    uploaded = st.sidebar.file_uploader("Upload CSV or Excel", type=["csv", "xlsx", "xls"])
    if st.sidebar.button("Load sample data", use_container_width=True):
        st.session_state.data = sample_data()
        st.session_state.source_name = "Built-in sample"
        st.session_state.selected_indices = set(st.session_state.data.index)
        st.session_state.pop("advanced_expression", None)
        st.session_state.pop("advanced_result", None)
        st.rerun()
    if uploaded is not None:
        try:
            raw = uploaded.getvalue()
            sheet = None
            if uploaded.name.lower().endswith((".xlsx", ".xls")):
                _, sheets = read_uploaded_file(raw, uploaded.name)
                sheet = st.sidebar.selectbox("Sheet", sheets, key=f"sheet_{uploaded.name}")
            frame, _ = read_uploaded_file(raw, uploaded.name, sheet)
            if st.session_state.get("source_name") != uploaded.name or st.session_state.get("data") is None:
                st.session_state.selected_indices = set(frame.index)
                st.session_state.rules = []
                st.session_state.pop("advanced_expression", None)
                st.session_state.pop("advanced_result", None)
            st.session_state.data = frame
            st.session_state.source_name = uploaded.name
        except Exception as exc:
            st.sidebar.error(str(exc))

    st.markdown(
        '<div class="hero"><h1>Element Selector</h1>'
        '<p>Filter data by condition.</p></div>',
        unsafe_allow_html=True,
    )
    data_tab, conditions_tab = st.tabs(["Data", "Conditions"])
    df = st.session_state.data

    with data_tab:
        if df is None:
            st.markdown("### Your data")
            st.info("Upload a CSV or Excel file from the sidebar, or load the sample data.")
        elif df.empty:
            st.warning("The file loaded, but it contains no data rows.")
        else:
            st.markdown(f"### {st.session_state.get('source_name', 'Your data')}")
            left, right = st.columns(2)
            left.metric("Rows", f"{len(df):,}")
            right.metric("Columns", f"{len(df.columns):,}")
            with st.expander("Column types", expanded=False):
                types = pd.DataFrame({
                    "Column": [str(c) for c in df.columns],
                    "Type": [detect_type(df[c]) for c in df.columns],
                })
                st.dataframe(types, use_container_width=True, hide_index=True)
            st.dataframe(df, use_container_width=True, hide_index=True, height=480)

    with conditions_tab:
        if df is None:
            st.info("Load your data in the Data tab first. Then add a condition here.")
            return
        if df.empty:
            st.info("There are no rows to filter.")
            return

        st.markdown("### What should be selected?")
        st.caption("Add one or more rules. Choose AND when every rule must match, or OR when any rule can match.")
        if st.session_state.rules:
            st.session_state.combine = st.radio(
                "Match", ["AND", "OR"], horizontal=True, key="combine",
                help="AND = all rules. OR = at least one rule.",
            )
        for i in range(len(st.session_state.rules)):
            rule = render_rule(i, df)
            if rule:
                st.session_state.rules[i] = rule
        add_col, clear_col = st.columns([1, 1])
        if add_col.button("＋ Add condition", type="primary", use_container_width=True):
            st.session_state.rules.append({})
            st.rerun()
        if st.session_state.rules and clear_col.button("Clear conditions", use_container_width=True):
            st.session_state.rules = []
            st.rerun()

        with st.expander("Advanced condition or saved presets", expanded=False):
            advanced = st.toggle("Use advanced expression", key="compact_advanced")
            if advanced:
                expression = st.text_input(
                    "Condition", placeholder="dc_ratio > 1 and type == 'Column'",
                    help="Column names, comparisons, and AND/OR only. No Python code.",
                )
                if st.button("Apply expression"):
                    try:
                        result = apply_advanced_query(df, expression)
                        st.session_state.advanced_expression = expression
                        st.session_state.advanced_result = result
                        st.session_state.selected_indices = set(result.index)
                        st.success("Expression applied.")
                    except ValueError as exc:
                        st.error(str(exc))
            else:
                st.session_state.pop("advanced_expression", None)
                st.session_state.pop("advanced_result", None)
            st.markdown("**Presets**")
            preset_name = st.text_input("Preset name", placeholder="e.g. High demand ratio", key="compact_preset_name")
            p1, p2 = st.columns(2)
            if p1.button("Save preset"):
                if not preset_name.strip():
                    st.warning("Enter a preset name first.")
                else:
                    st.session_state.presets[preset_name.strip()] = {
                        "combine": st.session_state.get("combine", "AND"),
                        "conditions": st.session_state.rules,
                    }
                    st.success("Preset saved for this session.")
            if st.session_state.presets:
                chosen = p2.selectbox("Load preset", list(st.session_state.presets), key="compact_load_preset")
                if p2.button("Load", key="compact_load_button"):
                    preset = st.session_state.presets[chosen]
                    st.session_state.rules = preset["conditions"]
                    st.session_state.combine = preset.get("combine", "AND")
                    st.rerun()
            import_file = st.file_uploader("Import preset JSON", type=["json"], key="compact_preset_import")
            if import_file is not None:
                try:
                    preset = json.loads(import_file.getvalue().decode("utf-8"))
                    st.session_state.rules = preset["conditions"]
                    st.session_state.combine = preset.get("combine", "AND")
                    st.success("Preset loaded.")
                except Exception as exc:
                    st.error(f"Could not read preset: {exc}")
            if preset_name.strip() in st.session_state.presets:
                preset_json = json.dumps(st.session_state.presets[preset_name.strip()], indent=2, default=str)
                st.download_button("Export preset JSON", preset_json, file_name="conditions.json", mime="application/json")

        try:
            if st.session_state.get("advanced_expression") and st.session_state.get("advanced_result") is not None:
                matched = st.session_state.advanced_result
            else:
                matched = apply_conditions(df, st.session_state.rules, st.session_state.get("combine", "AND"))
        except Exception as exc:
            st.error(str(exc))
            matched = df.iloc[0:0].copy()

        chosen_rows = matched.loc[matched.index.isin(st.session_state.selected_indices)].copy()
        percent = (100 * len(matched) / len(df)) if len(df) else 0
        st.markdown("---")
        st.markdown("### Matching rows")
        st.caption(f"{len(matched):,} of {len(df):,} rows match ({percent:.1f}%).")
        if matched.empty:
            st.info("No rows match yet. Change or add a condition above.")
        else:
            editable = matched.copy()
            editable.insert(0, "Select", [idx in st.session_state.selected_indices for idx in editable.index])
            edited = st.data_editor(
                editable, use_container_width=True, hide_index=True,
                disabled=[c for c in editable.columns if c != "Select"],
                column_config={"Select": st.column_config.CheckboxColumn("Select", default=True)},
                key="compact_result_editor",
            )
            picked = {idx for idx, selected in zip(matched.index, edited["Select"].fillna(False).tolist()) if selected}
            st.session_state.selected_indices = (st.session_state.selected_indices - set(matched.index)) | picked
            chosen_rows = matched.loc[matched.index.isin(picked)].copy()
            st.caption(f"Selected {len(chosen_rows):,} rows for export.")
            with st.expander("Download selected rows"):
                id_col = st.selectbox("ID column (optional)", ["— none —"] + [str(c) for c in df.columns])
                d1, d2 = st.columns(2)
                d1.download_button(
                    "Excel", to_excel_bytes(chosen_rows), file_name="selected_elements.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    disabled=chosen_rows.empty, use_container_width=True,
                )
                d2.download_button(
                    "CSV", chosen_rows.to_csv(index=False).encode("utf-8-sig"),
                    file_name="selected_elements.csv", mime="text/csv",
                    disabled=chosen_rows.empty, use_container_width=True,
                )
                if id_col != "— none —":
                    ids = chosen_rows[id_col].dropna().astype(str).tolist()
                    st.text_area("IDs (comma-separated)", ", ".join(ids), height=70)
                    st.download_button("Download IDs", "\n".join(ids), file_name="selected_ids.txt", mime="text/plain")


if __name__ == "__main__":
    main()
