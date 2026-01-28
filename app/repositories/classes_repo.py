import json
import pandas as pd
import gspread
from gspread.exceptions import WorksheetNotFound, APIError
from dataclasses import asdict
from app.services.gsheets_client import get_spreadsheet
from app.models.classes import Classes
from app.config import CLASSES_HEADERS, CLASSES_TAB
from app.utils.rate_parser import parse_rate_expr
import streamlit as st
# -----------------------------
# Sheet helpers for Classes

def get_or_create_worksheet(sh, tab_name: str):
    """
    Cached per Streamlit session to avoid repeated fetch_sheet_metadata calls.
    """
    cache = st.session_state.setdefault("_ws_cache", {})

    # Key by spreadsheet id + tab name
    key = (sh.id, tab_name)
    if key in cache:
        return cache[key]

    try:
        ws = sh.worksheet(tab_name)  # this triggers metadata read (expensive)
    except WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=50)

    cache[key] = ws
    return ws

def ensure_headers(ws, headers):
    values = ws.get_all_values()
    if not values:
        ws.update("A1", [headers])
        return
    if values[0] != headers:
        ws.update("A1", [headers])

def _parse_mct_id(s: str, prefix: str) -> int | None:
    # Accepts e.g. MCT001, MCT12, MCT0007
    if not isinstance(s, str):
        return None
    s = s.strip()
    if not s.startswith(prefix):
        return None
    tail = s[len(prefix):]
    if not tail.isdigit():
        return None
    return int(tail)

def next_class_id(ws, prefix: str = "MCT", width: int = 3) -> str:
    """
    Reads existing class_id values in column A (assuming header in row 1),
    returns next ID like MCT001, MCT002, ...
    """
    # Grab first column values (A) including header
    col = ws.col_values(1)  # 1-indexed
    if len(col) <= 1:
        return f"{prefix}{1:0{width}d}"

    nums = []
    for v in col[1:]:
        n = _parse_mct_id(v, prefix)
        if n is not None:
            nums.append(n)

    nxt = (max(nums) + 1) if nums else 1
    return f"{prefix}{nxt:0{width}d}"

def append_class_to_sheet(new_class: Classes):
    sh = get_spreadsheet()
    ws = get_or_create_worksheet(sh, CLASSES_TAB)
    ensure_headers(ws, CLASSES_HEADERS)

    row_dict = asdict(new_class)
    row = [row_dict.get(h, "") for h in CLASSES_HEADERS]
    ws.append_row(row, value_input_option="RAW")

def load_classes_df() -> pd.DataFrame:
    sh = get_spreadsheet()
    ws = get_or_create_worksheet(sh, CLASSES_TAB)
    ensure_headers(ws, CLASSES_HEADERS)

    records = ws.get_all_records()
    df = pd.DataFrame(records) if records else pd.DataFrame(columns=CLASSES_HEADERS)
    if "rate" in df.columns:
        # Keep the original expression as text (prevents Arrow int64 inference)
        df["rate"] = df["rate"].astype("string")

        # Numeric value for calculations
        def _to_rate_value(x):
            if x is None:
                return None
            s = str(x).strip()
            if s == "":
                return None
            try:
                return parse_rate_expr(s)
            except Exception:
                return None

    df["rate_value"] = df["rate"].apply(_to_rate_value)
    # Pretty display: decode and merge weekdays+durations
    if not df.empty:
        def _pretty_row(r):
            try:
                days = json.loads(r.get("week_day", "[]") or "[]")
                durs = json.loads(r.get("duration_hours", "[]") or "[]")
                pairs = [f"{d}:{h}h" for d, h in zip(days, durs)]
                return ", ".join(pairs)
            except Exception:
                return ""
        df["schedule"] = df.apply(_pretty_row, axis=1)

    return df