# app/repositories/sessions_repo.py
import pandas as pd
import pytz
from datetime import datetime
from dataclasses import asdict
from typing import Iterable

from app.services.gsheets_client import get_spreadsheet
from app.repositories.classes_repo import get_or_create_worksheet, ensure_headers
from app.config import SESSIONS_TAB, SESSIONS_HEADERS


def load_sessions_df() -> pd.DataFrame:
    sh = get_spreadsheet()
    ws = get_or_create_worksheet(sh, SESSIONS_TAB)
    ensure_headers(ws, SESSIONS_HEADERS)

    records = ws.get_all_records()
    df = pd.DataFrame(records) if records else pd.DataFrame(columns=SESSIONS_HEADERS)
    return df


def append_sessions(rows: list[list]):
    sh = get_spreadsheet()
    ws = get_or_create_worksheet(sh, SESSIONS_TAB)
    ensure_headers(ws, SESSIONS_HEADERS)

    if rows:
        ws.append_rows(rows, value_input_option="RAW")


def overwrite_sessions_df(df_all: pd.DataFrame) -> None:
    """
    Simple + reliable approach: rewrite the whole Sessions sheet.
    Fine for small/medium datasets.
    """
    sh = get_spreadsheet()
    ws = get_or_create_worksheet(sh, SESSIONS_TAB)
    ensure_headers(ws, SESSIONS_HEADERS)

    df_all = df_all.copy()
    # Ensure all columns exist + ordered
    for c in SESSIONS_HEADERS:
        if c not in df_all.columns:
            df_all[c] = ""
    df_all = df_all[SESSIONS_HEADERS]

    values = [SESSIONS_HEADERS] + df_all.astype(str).values.tolist()
    ws.clear()
    ws.update("A1", values)
