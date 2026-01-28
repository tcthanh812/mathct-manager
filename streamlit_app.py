import pandas as pd
import streamlit as st
import gspread
from gspread.exceptions import WorksheetNotFound, APIError
from dataclasses import dataclass, asdict
from datetime import datetime, date
import pytz
from typing import Optional
import uuid

from app.services.gsheets_client import get_gsheets_client, get_spreadsheet
from app.models.classes import Classes
from app.config import CLASSES_HEADERS, CLASSES_TAB, WEEKDAYS
from app.repositories.classes_repo import (
    get_or_create_worksheet,
    ensure_headers,
    next_class_id,
    append_class_to_sheet,
    load_classes_df,
)   
from app.ui.state import (
    init_state_if_missing,
    add_schedule_row,
    remove_schedule_row,
    mark_reset,
    apply_reset_if_marked)

import json
from datetime import timedelta

def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"

def refresh_classes_cache():
    st.session_state["classes_df_cache"] = load_classes_df()
    st.session_state["classes_cache_ready"] = True

def refresh_sessions_cache(month_first: date):
    # Call Sheets ONLY here
    _ensure_month_sessions_exist(month_first)

    sessions_df = load_sessions_df()
    sessions_df["session_date_dt"] = pd.to_datetime(sessions_df["session_date"], errors="coerce")

    first, last = _month_bounds(month_first)
    month_df = sessions_df[
        (sessions_df["session_date_dt"] >= pd.Timestamp(first))
        & (sessions_df["session_date_dt"] <= pd.Timestamp(last))
    ].copy()

    # Normalize types for editor
    if not month_df.empty:
        month_df["actual_duration_hours"] = pd.to_numeric(month_df["actual_duration_hours"], errors="coerce").fillna(0.0)
        month_df["rate"] = pd.to_numeric(month_df["rate"], errors="coerce").fillna(0.0)
        month_df["session_date"] = pd.to_datetime(month_df["session_date"], errors="coerce").dt.date

    st.session_state["sessions_df_full_cache"] = sessions_df
    st.session_state["sessions_month_df_cache"] = month_df
    st.session_state["sessions_month_key_cache"] = _month_key(month_first)
    st.session_state["sessions_cache_ready"] = True

SESSIONS_TAB = "Sessions"
SESSIONS_HEADERS = [
    "session_id",
    "class_id",
    "class_name",
    "session_date",           # YYYY-MM-DD
    "weekday",                # Mon/Tue...
    "planned_duration_hours",
    "actual_duration_hours",  # editable
    "rate",                   # editable
    "fee",                    # computed
    "status",                 # editable
    "note",                   # editable
    "created_at_utc",
    "updated_at_utc",
]

_WEEKDAY_TO_INT = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
_INT_TO_WEEKDAY = {v: k for k, v in _WEEKDAY_TO_INT.items()}


def _parse_rate(x) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if not s:
        return 0.0
    s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return 0.0


def _parse_iso_date(s: str):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _month_bounds(d: date) -> tuple[date, date]:
    first = d.replace(day=1)
    if first.month == 12:
        next_month = first.replace(year=first.year + 1, month=1, day=1)
    else:
        next_month = first.replace(month=first.month + 1, day=1)
    last = next_month - timedelta(days=1)
    return first, last


def load_sessions_df() -> pd.DataFrame:
    sh = get_spreadsheet()
    ws = get_or_create_worksheet(sh, SESSIONS_TAB)
    ensure_headers(ws, SESSIONS_HEADERS)
    records = ws.get_all_records()
    return pd.DataFrame(records) if records else pd.DataFrame(columns=SESSIONS_HEADERS)


def append_sessions(rows: list[list]) -> None:
    if not rows:
        return
    sh = get_spreadsheet()
    ws = get_or_create_worksheet(sh, SESSIONS_TAB)
    ensure_headers(ws, SESSIONS_HEADERS)
    ws.append_rows(rows, value_input_option="RAW")


def overwrite_sessions_df(df_all: pd.DataFrame) -> None:
    sh = get_spreadsheet()
    ws = get_or_create_worksheet(sh, SESSIONS_TAB)
    ensure_headers(ws, SESSIONS_HEADERS)

    df_all = df_all.copy()
    for c in SESSIONS_HEADERS:
        if c not in df_all.columns:
            df_all[c] = ""
    df_all = df_all[SESSIONS_HEADERS]

    values = [SESSIONS_HEADERS] + df_all.astype(str).values.tolist()
    ws.clear()
    ws.update("A1", values)


def _generate_sessions_for_month(classes_df: pd.DataFrame, month_first: date) -> pd.DataFrame:
    first, last = _month_bounds(month_first)
    days = pd.date_range(first, last, freq="D")

    out = []
    now_utc = datetime.now(pytz.UTC).isoformat()

    for _, r in classes_df.iterrows():
        class_id = str(r.get("class_id", "")).strip()
        class_name = str(r.get("class_name", "")).strip()
        rate = _parse_rate(r.get("rate", 0))

        sd = _parse_iso_date(r.get("start_date", ""))
        ed = _parse_iso_date(r.get("end_date", ""))

        # Your Classes sheet stores week_day and duration_hours as JSON strings
        try:
            week_days = json.loads(r.get("week_day", "[]") or "[]")
        except Exception:
            week_days = []
        try:
            durations = json.loads(r.get("duration_hours", "[]") or "[]")
        except Exception:
            durations = []

        schedule = {}
        for dname, dur in zip(week_days, durations):
            if dname in _WEEKDAY_TO_INT:
                try:
                    schedule[dname] = float(dur)
                except Exception:
                    schedule[dname] = 0.0

        if not class_id or not schedule:
            continue

        for day_ts in days:
            dt = day_ts.date()

            if sd and dt < sd:
                continue
            if ed and dt > ed:
                continue

            wd = _INT_TO_WEEKDAY.get(dt.weekday())
            if wd not in schedule:
                continue

            planned = float(schedule[wd])
            if planned <= 0:
                continue

            out.append(
                {
                    "session_id": str(uuid.uuid4()),
                    "class_id": class_id,
                    "class_name": class_name,
                    "session_date": dt.isoformat(),
                    "weekday": wd,
                    "planned_duration_hours": planned,
                    "actual_duration_hours": planned,
                    "rate": rate,
                    "fee": planned * rate,
                    "status": "planned",
                    "note": "",
                    "created_at_utc": now_utc,
                    "updated_at_utc": now_utc,
                }
            )

    df = pd.DataFrame(out)
    if df.empty:
        return pd.DataFrame(columns=SESSIONS_HEADERS)
    for c in SESSIONS_HEADERS:
        if c not in df.columns:
            df[c] = ""
    return df[SESSIONS_HEADERS]


def _ensure_month_sessions_exist(month_first: date) -> None:
    classes_df = load_classes_df()
    sessions_df = load_sessions_df()

    planned_df = _generate_sessions_for_month(classes_df, month_first)
    if planned_df.empty:
        return

    if sessions_df.empty:
        existing_keys = set()
    else:
        sessions_df["class_id"] = sessions_df["class_id"].astype(str)
        sessions_df["session_date"] = sessions_df["session_date"].astype(str)
        existing_keys = set(zip(sessions_df["class_id"], sessions_df["session_date"]))

    to_add = planned_df[
        ~planned_df.apply(lambda r: (str(r["class_id"]), str(r["session_date"])) in existing_keys, axis=1)
    ].copy()

    if to_add.empty:
        return

    append_sessions(to_add.astype(str).values.tolist())

# -----------------------------
# Sheet helpers
# -----------------------------
def require_password():
    if st.session_state.get("authenticated"):
        return

    with st.form("login"):
        pw = st.text_input("Password", type="password")
        ok = st.form_submit_button("Login")

    if not ok:
        st.stop()

    if pw == st.secrets["APP_PASSWORD"]:
        st.session_state["authenticated"] = True
        st.rerun()
    else:
        st.error("Incorrect password")
        st.stop()

require_password()


# -----------------------------
# Streamlit UI (no st.form; preserves values on Add/Remove)
# -----------------------------
tab_classes, tab_sessions = st.tabs(["Classes", "Monthly Sessions"])

with tab_classes:
    # ---- PASTE YOUR CURRENT CLASSES UI HERE (UNCHANGED) ----
    # Init
    init_state_if_missing()
    apply_reset_if_marked()

    class_name = st.text_input("Class name", key="class_name")
    rate = st.text_input("Rate", key="rate")

    c1, c2 = st.columns(2)
    with c1:
        start_date = st.date_input("Start date (optional)", value=None, key="start_date")
    with c2:
        end_date = st.date_input("End date (optional)", value=None, key="end_date")

    st.markdown("**Schedule** (weekday + duration in hours)")

    b1, b2, _ = st.columns([1, 3, 7])
    with b1:
        st.button("Add", on_click=add_schedule_row, key="add_weekday_btn")
    with b2:
        st.button("Reset", on_click=mark_reset, key="reset_all_btn")

    for row in st.session_state["schedule_rows"]:
        rid = row["row_id"]
        col1, col2, col3 = st.columns([2, 2, 1])

        with col1:
            day = st.selectbox(
                "Weekday",
                WEEKDAYS,
                index=WEEKDAYS.index(row["day"]) if row["day"] in WEEKDAYS else 0,
                key=f"day_{rid}",
                label_visibility="collapsed",
            )

        with col2:
            duration = st.number_input(
                "Duration (hours)",
                min_value=0.25,
                max_value=8.0,
                value=float(row["duration"]),
                step=0.25,
                key=f"dur_{rid}",
                label_visibility="collapsed",
            )

        with col3:
            st.button("Remove", on_click=remove_schedule_row, args=(rid,), key=f"remove_{rid}")

        row["day"] = day
        row["duration"] = float(duration)

    if st.button("Create class", key="create_class_btn"):
        if not class_name.strip():
            st.error("Class name is required.")
        elif start_date is not None and end_date is not None and end_date < start_date:
            st.error("End date must be on/after start date.")
        else:
            week_day = [r["day"] for r in st.session_state["schedule_rows"]]
            duration_hours = [r["duration"] for r in st.session_state["schedule_rows"]]

            if not week_day:
                st.error("Please add at least one schedule row.")
            elif len(set(week_day)) != len(week_day):
                st.error("Duplicate weekdays found. Each weekday should appear at most once.")
            elif any(d <= 0 for d in duration_hours):
                st.error("Duration must be > 0 hours for every row.")
            else:
                sh = get_spreadsheet()
                ws = get_or_create_worksheet(sh, CLASSES_TAB)
                ensure_headers(ws, CLASSES_HEADERS)

                class_id = next_class_id(ws, prefix="MCT", width=3)

                new_class = Classes.create(
                    class_id=class_id,
                    class_name=class_name,
                    rate=rate,
                    start_date=start_date,
                    end_date=end_date,
                    week_day=week_day,
                    duration_hours=duration_hours,
                )
                append_class_to_sheet(new_class)

                refresh_classes_cache()

                st.success(f"Created: {new_class.class_id} — {new_class.class_name}")
                st.session_state["_do_reset"] = True
                st.rerun()

    st.subheader("Existing classes")
    if not st.session_state.get("classes_cache_ready"):
        refresh_classes_cache()

    df = st.session_state["classes_df_cache"]
    preferred_cols = ["class_id", "class_name", "rate", "start_date", "end_date", "schedule", "created_at_utc"]
    st.dataframe(
        df[preferred_cols] if (not df.empty and all(c in df.columns for c in preferred_cols)) else df,
        use_container_width=True,
    )


with tab_sessions:
    st.header("Monthly Sessions")

    # Month picker (defaults to this month)
    today = date.today()
    month_first = st.date_input(
        "Month",
        value=today.replace(day=1),
        help="Pick any date in the month; the app uses that month.",
        key="sessions_month",
    ).replace(day=1)

    # Ensure Sessions exist for selected month (idempotent)
    _ensure_month_sessions_exist(month_first)
    mk = _month_key(month_first)
    if (
        not st.session_state.get("sessions_cache_ready")
        or st.session_state.get("sessions_month_key_cache") != mk
    ):
        refresh_sessions_cache(month_first)
    # Load Sessions + filter to month
    sessions_df = st.session_state["sessions_df_full_cache"]
    month_df = st.session_state["sessions_month_df_cache"]

    if month_df.empty:
        st.info("No sessions in this month.")
        st.stop()

    first, last = _month_bounds(month_first)
    sessions_df["session_date_dt"] = pd.to_datetime(sessions_df["session_date"], errors="coerce")

    month_df = sessions_df[
        (sessions_df["session_date_dt"] >= pd.Timestamp(first))
        & (sessions_df["session_date_dt"] <= pd.Timestamp(last))
    ].copy()

    if month_df.empty:
        st.info("No sessions in this month.")
        st.stop()

    # Normalize numeric fields
    month_df["actual_duration_hours"] = pd.to_numeric(month_df["actual_duration_hours"], errors="coerce").fillna(0.0)
    month_df["rate"] = pd.to_numeric(month_df["rate"], errors="coerce").fillna(0.0)

    # Make session_date editable as proper date type in editor
    month_df["session_date"] = pd.to_datetime(month_df["session_date"], errors="coerce").dt.date

    # We show fee_display (string), compute fee_raw (numeric) for save + totals
    show_cols = ["session_date", "weekday", "actual_duration_hours", "rate", "fee_display", "status", "note"]

    # Helpers for saving one class at a time
    def _format_fee_display(fee_raw_series: pd.Series) -> pd.Series:
        fee_vnd = (pd.to_numeric(fee_raw_series, errors="coerce").fillna(0.0) * 1000).round(0).astype(int)
        return fee_vnd.map(lambda x: f"{x:,}")

    def _save_class_changes(class_edited: pd.DataFrame, sessions_df_full: pd.DataFrame) -> None:
        """
        class_edited must contain: session_id, session_date_iso, actual_duration_hours, rate, status, note, fee_raw
        """
        if class_edited.empty:
            st.warning("Nothing to save for this class.")
            return

        full = sessions_df_full.copy()
        if "session_id" not in full.columns:
            st.error("Sessions sheet is missing 'session_id' column.")
            return

        full["session_id"] = full["session_id"].astype(str)

        now_utc = datetime.now(pytz.UTC).isoformat()
        update_map = (
            class_edited.set_index("session_id")[["session_date_iso", "actual_duration_hours", "rate", "status", "note", "fee_raw"]]
            .to_dict("index")
        )

        def _apply_row(row):
            sid = str(row.get("session_id", ""))
            if sid in update_map:
                row["session_date"] = str(update_map[sid].get("session_date_iso", row.get("session_date", "")) or "")
                row["actual_duration_hours"] = float(update_map[sid].get("actual_duration_hours", row.get("actual_duration_hours", 0)) or 0)
                row["rate"] = float(update_map[sid].get("rate", row.get("rate", 0)) or 0)
                row["status"] = str(update_map[sid].get("status", row.get("status", "")) or "")
                row["note"] = str(update_map[sid].get("note", row.get("note", "")) or "")
                row["fee"] = float(update_map[sid].get("fee_raw", 0) or 0)  # store raw in sheet
                row["updated_at_utc"] = now_utc
            return row

        full = full.apply(_apply_row, axis=1)

        for c in SESSIONS_HEADERS:
            if c not in full.columns:
                full[c] = ""
        full = full[SESSIONS_HEADERS]

        overwrite_sessions_df(full)
        st.success("Saved changes for this class.")

        # mark cache dirty so next run reloads from Sheets ONCE
        st.session_state["sessions_cache_ready"] = False
        st.rerun()

    # ---- Render per-class tables with per-table Save button ----
    edited_all_for_totals = []
    grouped = month_df.groupby(["class_id", "class_name"], sort=True)

    for (cid, cname), g in grouped:
        g = g.copy()

        if "session_id" not in g.columns:
            st.error("Sessions sheet is missing 'session_id' column.")
            st.stop()

        session_ids = g["session_id"].astype(str).tolist()

        # Compute fee display (fee_raw * 1000 with commas)
        g["fee_raw"] = g["actual_duration_hours"] * g["rate"]
        g["fee_display"] = _format_fee_display(g["fee_raw"])

        st.subheader(f"{cid} — {cname}")

        editor_df = g[show_cols].copy()  # session_id hidden

        edited_g = st.data_editor(
            editor_df,
            use_container_width=True,
            num_rows="fixed",
            disabled=["weekday", "fee_display"],  # session_date editable
            column_config={
                "session_date": st.column_config.DateColumn("Session date"),
                "actual_duration_hours": st.column_config.NumberColumn("Actual (hours)", format="%.2f"),
                "rate": st.column_config.NumberColumn("Rate", format="%.2f"),
                "fee_display": st.column_config.TextColumn("Fee"),
                "status": st.column_config.TextColumn("Status"),
                "note": st.column_config.TextColumn("Note"),
            },
            hide_index=True,
            key=f"sessions_editor_{cid}",
        )

        # Reattach session_id by row order
        edited_g = edited_g.copy()
        if len(edited_g) != len(session_ids):
            st.error("Row count changed; cannot map edits back to session IDs.")
            st.stop()

        edited_g.insert(0, "session_id", session_ids)

        # Normalize edited values
        edited_g["actual_duration_hours"] = pd.to_numeric(edited_g["actual_duration_hours"], errors="coerce").fillna(0.0)
        edited_g["rate"] = pd.to_numeric(edited_g["rate"], errors="coerce").fillna(0.0)

        edited_g["session_date"] = pd.to_datetime(edited_g["session_date"], errors="coerce").dt.date
        if edited_g["session_date"].isna().any():
            st.error("Invalid session_date detected. Please fix the date values.")
            st.stop()
        edited_g["session_date_iso"] = edited_g["session_date"].map(lambda d: d.isoformat())

        # Recompute fees
        edited_g["fee_raw"] = edited_g["actual_duration_hours"] * edited_g["rate"]
        edited_g["fee_display"] = _format_fee_display(edited_g["fee_raw"])

        # Keep for monthly totals across all classes
        edited_all_for_totals.append(edited_g[["session_id", "actual_duration_hours", "fee_raw"]].copy())

        # Save button directly under this table (per class)
        if st.button("Save changes", type="primary", key=f"save_class_{cid}"):
            _save_class_changes(
                class_edited=edited_g[["session_id", "session_date_iso", "actual_duration_hours", "rate", "status", "note", "fee_raw"]].copy(),
                sessions_df_full=sessions_df,
            )

        st.divider()

    # ---- Overall aggregate at top (based on current edited values) ----
    # Note: this will render AFTER the tables. If you want it at the very top,
    # we can compute a "best effort" total from month_df before editing instead.
    if edited_all_for_totals:
        all_totals_df = pd.concat(edited_all_for_totals, ignore_index=True)
        total_sessions = int(len(all_totals_df))
        total_hours = float(pd.to_numeric(all_totals_df["actual_duration_hours"], errors="coerce").fillna(0.0).sum())
        total_fee = float(pd.to_numeric(all_totals_df["fee_raw"], errors="coerce").fillna(0.0).sum() * 1000)
    else:
        total_sessions, total_hours, total_fee = 0, 0.0, 0.0

    st.subheader("Monthly Total")
    c1, c2, c3 = st.columns(3)
    c1.metric("Sessions", total_sessions)
    c2.metric("Total hours", round(total_hours, 2))
    c3.metric("Total fee", f"{int(round(total_fee)):,}")





