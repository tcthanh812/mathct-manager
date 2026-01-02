import streamlit as st
import pandas as pd
import numpy as np
import calendar
from supabase import create_client


@st.cache_resource
def require_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        pw = st.text_input("Password", type="password")
        if pw == st.secrets["APP_PASSWORD"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.stop()

@st.cache_resource
def supa():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

TABLE = "schedule_overrides"

def load_override(class_name: str, year: int, month: int) -> pd.DataFrame | None:
    resp = (
        supa().table(TABLE)
        .select("data")
        .eq("class_name", class_name)
        .eq("year", int(year))
        .eq("month", int(month))
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        return None
    df = pd.DataFrame(rows[0]["data"])
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df

def save_override(class_name: str, year: int, month: int, df: pd.DataFrame) -> None:
    df2 = df.copy()

    # Make JSON-safe
    if "Date" in df2.columns:
        df2["Date"] = pd.to_datetime(df2["Date"], errors="coerce").dt.strftime("%Y-%m-%d")

    payload = {
        "class_name": class_name,
        "year": int(year),
        "month": int(month),
        "data": df2.to_dict(orient="records"),
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }

    supa().table(TABLE).upsert(payload, on_conflict="class_name,year,month").execute()

def delete_override(class_name: str, year: int, month: int) -> None:
    supa().table(TABLE).delete().eq("class_name", class_name).eq("year", int(year)).eq("month", int(month)).execute()


classes = {
    "Stella": {
        "rate": 450,
        # [DayName, Duration, StartDate, EndDate]
        "class": [["Saturday",2,"2025-12-27",""],
                  ["Sunday",2,"","2026-02-01"],
        ]
    },
    "Điền": {
        "rate": 450,
        "class": [["Tuesday",1,"",""],
                  ["Thursday",1,"",""],
        ]
    }
}
require_password()
def is_active(date: pd.Timestamp, start_str: str, end_str: str) -> bool:
    if start_str and date < pd.Timestamp(start_str):
        return False
    if end_str and date > pd.Timestamp(end_str):
        return False
    return True

def build_base_schedule(details: dict, year: int, month: int) -> pd.DataFrame:
    rate = float(details["rate"])
    days_in_month = calendar.monthrange(year, month)[1]
    rows = []

    for d in range(1, days_in_month + 1):
        date = pd.Timestamp(year, month, d)
        day_name = date.day_name()

        for rule_day, duration, start_str, end_str in details["class"]:
            if day_name != rule_day:
                continue
            if not is_active(date, start_str, end_str):
                continue

            duration = float(duration)
            rows.append({
                "Date": date,
                "Day": day_name,
                "Class Duration (hrs)": duration,
                "Rate": rate,
                "Fee": rate * duration,
                "Note": "",
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Date").reset_index(drop=True)
    return df

# -----------------------------
# UI: Month-Year selector (default previous month)
# -----------------------------
st.title("Schedule")

today = pd.Timestamp.today()
default_date = (today - pd.DateOffset(months=1)).replace(day=1)
selected_date = st.date_input("Select month & year", value=default_date)

year = selected_date.year
month = selected_date.month

grand_total = 0.0

for class_name, details in classes.items():
    st.header(class_name)
    st.subheader(f"Rate: {details['rate']}/hr")

    base_df = build_base_schedule(details, year, month)
    override_df = load_override(class_name, year, month)

    df_to_edit = override_df if override_df is not None else base_df

    if df_to_edit.empty:
        st.write("No classes scheduled for this month.")
        continue

    edited = st.data_editor(
        df_to_edit,
        num_rows="dynamic",             # add/remove rows
        use_container_width=True,
        key=f"editor_{class_name}_{year}_{month}",
    )

    # Keep Fee consistent if user edits Rate or Duration
    if {"Rate", "Class Duration (hrs)"}.issubset(edited.columns):
        edited["Fee"] = (
            pd.to_numeric(edited["Rate"], errors="coerce").fillna(0)
            * pd.to_numeric(edited["Class Duration (hrs)"], errors="coerce").fillna(0)
        )

    total_fee = float(pd.to_numeric(edited.get("Fee", 0), errors="coerce").fillna(0).sum())
    grand_total += total_fee

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("Save changes", key=f"save_{class_name}_{year}_{month}"):
            save_override(class_name, year, month, edited)
            st.success("Saved. This month will load the edited table next time.")
    with c2:
        if st.button("Reset to original", key=f"reset_{class_name}_{year}_{month}"):
            delete_override(class_name, year, month)
            st.success("Reset. This month will load the original generated schedule next time.")
    with c3:
        st.metric("Total fee (this class)", f"{total_fee:,.0f}")

st.divider()
st.metric("Grand total (all classes)", f"{grand_total:,.0f}")