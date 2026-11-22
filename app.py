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
    if "rules" not in st.session_state: st.session_state.rules = []
    if "data" not in st.session_state: st.session_state.data = None
    if "selected_indices" not in st.session_state: st.session_state.selected_indices = set()
    if "presets" not in st.session_state: st.session_state.presets = {}
    if "active_name" not in st.session_state: st.session_state.active_name = ""

    st.sidebar.markdown("### ⌖ Element Selector")
    st.sidebar.caption("A flexible filter desk for engineering tables and beyond.")
    uploaded = st.sidebar.file_uploader("1 · Upload a data file", type=["csv", "xlsx", "xls"], help="CSV and Excel spreadsheets are supported.")
    if st.sidebar.button("Load sample data", use_container_width=True, help="Try the selector with a small structural example"):
        st.session_state.data = sample_data()
        st.session_state.source_name = "Built-in sample"
        st.session_state.selected_indices = set(st.session_state.data.index)
        st.rerun()
    if uploaded is not None:
        try:
            data_bytes = uploaded.getvalue()
            sheets = ["CSV"]
            if uploaded.name.lower().endswith((".xlsx", ".xls")):
                _, sheets = read_uploaded_file(data_bytes, uploaded.name)
                sheet = st.sidebar.selectbox("Worksheet", sheets, key=f"sheet_{uploaded.name}")
            else:
                sheet = None
            frame, _ = read_uploaded_file(data_bytes, uploaded.name, sheet)
            st.session_state.data = frame
            st.session_state.source_name = uploaded.name
            st.session_state.selected_indices = set(frame.index)
        except Exception as exc:
            st.sidebar.error(str(exc))

    if st.session_state.data is None:
        st.markdown('<div class="hero"><div class="kicker">ENGINEERING DATA WORKBENCH</div><h1>Element Selector</h1><p>Filter any spreadsheet into a clean, auditable selection — no code required.</p></div>', unsafe_allow_html=True)
        st.markdown("### Start with your data")
        st.markdown('<div class="panel"><b>1 · Upload</b> a CSV or Excel workbook in the sidebar &nbsp; → &nbsp; <b>2 · Build conditions</b> with visual controls &nbsp; → &nbsp; <b>3 · Refine and export</b> the matching rows.</div>', unsafe_allow_html=True)
        st.info("No file loaded yet. Drop a .csv, .xlsx, or .xls file into the uploader, or load the built-in example.")
        return

    df = st.session_state.data
    if df.empty:
        st.warning("The file was read successfully, but it contains no data rows.")
        return
    st.markdown(f'<div class="hero"><div class="kicker">ELEMENT SELECTOR · {len(df):,} ROWS · {len(df.columns)} COLUMNS</div><h1>{st.session_state.get("source_name", "Your data")}</h1><p>Build a precise selection, review the matches, then export exactly what you need.</p></div>', unsafe_allow_html=True)
    tabs = st.tabs(["Data", "Conditions", "Results", "Insights"])

    with tabs[0]:
        st.markdown("### <span class='step'>1</span> Inspect your data", unsafe_allow_html=True)
        m1,m2,m3=st.columns(3); m1.metric("Rows",f"{len(df):,}"); m2.metric("Columns",f"{len(df.columns):,}"); m3.metric("File",st.session_state.get("source_name","Sample"))
        types=pd.DataFrame({"Column":[str(c) for c in df.columns],"Detected type":[detect_type(df[c]) for c in df.columns],"Non-empty values":[int(df[c].notna().sum()) for c in df.columns]})
        st.markdown("#### Column map")
        st.dataframe(types,use_container_width=True,hide_index=True,height=min(280,60+len(types)*36))
        st.markdown("#### Preview")
        st.dataframe(df.head(12),use_container_width=True,hide_index=True)

    with tabs[1]:
        st.markdown("### <span class='step'>2</span> Build your conditions", unsafe_allow_html=True)
        st.caption("Conditions are applied in the order shown. Choose AND to require every condition, or OR to match any one.")
        advanced=st.toggle("Advanced mode",help="Use a restricted pandas-style expression for multi-column logic.")
        if advanced:
            expression=st.text_area("Condition expression",placeholder="dc_ratio > 1 and type == 'Column'",help="Supports column names, comparisons, literals, and AND/OR. No functions or Python code.",height=100)
            if st.button("Apply advanced condition",type="primary"):
                try:
                    st.session_state.advanced_result=apply_advanced_query(df,expression)
                    st.session_state.advanced_expression=expression
                    st.session_state.selected_indices=set(st.session_state.advanced_result.index)
                    st.success(f"Condition applied: {len(st.session_state.advanced_result):,} matching rows.")
                except ValueError as exc: st.error(str(exc))
            st.caption("To reference a column with spaces, wrap it in backticks (for example, `Story Name` > 2).")
        else:
            st.session_state.pop("advanced_expression", None)
            st.session_state.pop("advanced_result", None)
            if st.session_state.rules:
                st.session_state.combine=st.radio("Combine conditions",["AND","OR"],horizontal=True,key="combine",help="AND requires all conditions; OR requires at least one.")
            for i in range(len(st.session_state.rules)):
                rule=render_rule(i,df)
                if rule: st.session_state.rules[i]=rule
            a,b=st.columns([1,3])
            if a.button("＋ Add condition",type="primary"): st.session_state.rules.append({}); st.rerun()
            if st.session_state.rules and b.button("Clear all conditions"): st.session_state.rules=[]; st.rerun()
            st.markdown("#### Saved presets")
            pname=st.text_input("Preset name",value=st.session_state.active_name,placeholder="e.g. Columns above capacity")
            c1,c2,c3=st.columns([1,1,1.3])
            if c1.button("Save preset"):
                if not pname.strip(): st.warning("Enter a name for this preset.")
                else:
                    st.session_state.presets[pname.strip()]={"combine":st.session_state.get("combine","AND"),"conditions":st.session_state.rules}
                    st.session_state.active_name=pname.strip(); st.success("Preset saved for this session.")
            if st.session_state.presets:
                names=list(st.session_state.presets)
                chosen=c2.selectbox("Load preset",names,label_visibility="collapsed")
                if c2.button("Load",key="load_preset"):
                    entry=st.session_state.presets[chosen]
                    st.session_state.rules=entry["conditions"]
                    st.session_state["combine"]=entry["combine"]
                    st.session_state.active_name=chosen
                    st.rerun()
            imported=c3.file_uploader("Import preset JSON",type=["json"],key="preset_import")
            if imported:
                try:
                    content=json.loads(imported.getvalue().decode("utf-8"))
                    if not isinstance(content,dict) or "conditions" not in content: raise ValueError("Expected a preset object with a conditions list.")
                    st.session_state.rules=content["conditions"]
                    st.session_state["combine"]=content.get("combine","AND")
                    st.success("Preset imported. Review the conditions, then apply them in Results.")
                except Exception as exc: st.error(f"Could not import preset: {exc}")
            if pname.strip() in st.session_state.presets:
                payload=json.dumps(st.session_state.presets[pname.strip()],indent=2,default=str)
                st.download_button("Export this preset as JSON",payload,file_name=f"{re.sub(r'[^A-Za-z0-9_-]+','_',pname.strip())}.json",mime="application/json")

    # Calculate current matched frame, preserving a friendly error instead of stopping the app.
    try:
        if st.session_state.get("advanced_expression") and st.session_state.get("advanced_result") is not None:
            matched=st.session_state.advanced_result
        else:
            matched=apply_conditions(df,st.session_state.rules,st.session_state.get("combine","AND"))
        filter_error=None
    except Exception as exc:
        matched=df.iloc[0:0].copy(); filter_error=str(exc)

    with tabs[2]:
        st.markdown("### <span class='step'>3</span> Review and export", unsafe_allow_html=True)
        if filter_error: st.error(filter_error)
        pct=100*len(matched)/len(df) if len(df) else 0
        m1,m2,m3=st.columns(3); m1.metric("Matching rows",f"{len(matched):,}"); m2.metric("Share of data",f"{pct:.1f}%"); m3.metric("Manually selected",f"{len(st.session_state.selected_indices & set(matched.index)):,}")
        if matched.empty: st.warning("No rows match these conditions. Try relaxing a condition or switching AND to OR.")
        view=st.radio("View",["Matches only","Highlight matches in full table"],horizontal=True)
        if view.startswith("Highlight"):
            tmp=df.copy(); tmp.insert(0,"Match",tmp.index.isin(matched.index).map({True:"✓ Match",False:"—"}))
            st.dataframe(tmp,use_container_width=True,hide_index=True)
        else:
            columns=st.multiselect("Columns to show",[str(c) for c in df.columns],default=[str(c) for c in df.columns],help="This affects the on-screen table. Exports include all source columns.")
            sort_col=st.selectbox("Sort by",["(original order)"]+[str(c) for c in matched.columns])
            display=matched.loc[:,columns] if columns else matched.iloc[:,0:0]
            if sort_col!="(original order)": display=display.sort_values(sort_col,kind="stable")
            # Keep an explicit checkbox field so the selection can be refined interactively.
            editable=display.copy()
            editable.insert(0,"Select",[idx in st.session_state.selected_indices for idx in editable.index])
            edited=st.data_editor(editable,use_container_width=True,hide_index=True,disabled=[c for c in editable.columns if c!="Select"],column_config={"Select":st.column_config.CheckboxColumn("Select",help="Check rows to include in downloads.",default=True)},key="result_editor")
            selected_idx=set(edited.index[edited["Select"].fillna(False)])
            # data_editor's hidden index is preserved for this view in Streamlit versions using index internally.
            # A stable row key keeps manual state aligned even when visible columns are changed/sorted.
            if len(selected_idx)==0 and "Select" in edited.columns:
                selected_idx={matched.index[i] for i,flag in enumerate(edited["Select"].fillna(False).tolist()) if flag and i<len(matched)}
            st.session_state.selected_indices=(st.session_state.selected_indices-set(matched.index))|selected_idx
        selected=matched.loc[matched.index.isin(st.session_state.selected_indices)].copy()
        st.caption(f"Selected {len(selected):,} of {len(df):,} rows ({100*len(selected)/len(df):.1f}%).")
        st.markdown("#### Export selected rows")
        id_col=st.selectbox("ID column (optional)",["— none —"]+[str(c) for c in df.columns],help="Choose the field containing element IDs for the ID-only export.")
        e1,e2,e3=st.columns(3)
        e1.download_button("Download Excel",to_excel_bytes(selected),file_name="selected_elements.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",disabled=selected.empty)
        e2.download_button("Download CSV",selected.to_csv(index=False).encode("utf-8-sig"),file_name="selected_elements.csv",mime="text/csv",disabled=selected.empty)
        ids=selected[id_col].dropna().astype(str).tolist() if id_col!="— none —" else []
        e3.download_button("Download IDs",("\n".join(ids)).encode("utf-8"),file_name="selected_ids.txt",mime="text/plain",disabled=not ids,help="Select an ID column first.")
        if ids:
            id_text=", ".join(ids)
            st.text_area("IDs · comma-separated",value=id_text,height=75,help="Select and copy this list. Clipboard write is browser-restricted in Streamlit.")
            st.caption("Tip: click the ID list, press Ctrl+A, then Ctrl+C to copy it.")

    with tabs[3]:
        st.markdown("### Quick insights")
        if matched.empty:
            st.info("Matching rows will appear here once you apply conditions.")
        else:
            cats=[str(c) for c in matched.columns if detect_type(matched[c])=="text"]
            nums=[str(c) for c in matched.columns if detect_type(matched[c])=="number"]
            if cats:
                cat=st.selectbox("Count by category",cats,key="insight_cat")
                counts=matched[cat].fillna("(empty)").astype(str).value_counts().head(20).rename_axis(cat).reset_index(name="Count")
                st.plotly_chart(px.bar(counts,x=cat,y="Count",color_discrete_sequence=["#167d8d"],title=f"Selected rows by {cat}"),use_container_width=True)
            if nums:
                num=st.selectbox("Numeric distribution",nums,key="insight_num")
                st.plotly_chart(px.histogram(matched,x=num,nbins=24,color_discrete_sequence=["#167d8d"],title=f"Distribution of {num}"),use_container_width=True)
            if not cats and not nums: st.caption("No category or numeric columns are available for charts.")

if __name__ == "__main__":
    main()
