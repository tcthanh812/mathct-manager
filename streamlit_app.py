import calendar
import pandas as pd
import streamlit as st
from supabase import create_client

# -----------------------------
# Password gate (NO caching here)
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
# Supabase client (safe to cache)
# -----------------------------
@st.cache_resource
def supa():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

WEEKDAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
TABLE_CLASSES = "classes"
TABLE_RULES = "class_rules"
TABLE_OVERRIDES = "schedule_overrides"

# -----------------------------
# DB helpers: Classes & Rules
# -----------------------------
def fetch_classes(active_only: bool) -> pd.DataFrame:
    q = supa().table(TABLE_CLASSES).select("*").order("class_name", desc=False)
    if active_only:
        q = q.eq("active", True)
    resp = q.execute()
    return pd.DataFrame(resp.data or [])

def upsert_class(row: dict) -> None:
    row = dict(row)
    row["updated_at"] = pd.Timestamp.utcnow().isoformat()
    supa().table(TABLE_CLASSES).upsert(row, on_conflict="id").execute()

def delete_class(class_id: str) -> None:
    supa().table(TABLE_CLASSES).delete().eq("id", class_id).execute()

def fetch_rules_for_class(class_id: str) -> pd.DataFrame:
    resp = (
        supa().table(TABLE_RULES)
        .select("*")
        .eq("class_id", class_id)
        .order("weekday", desc=False)
        .execute()
    )
    df = pd.DataFrame(resp.data or [])
    for col in ["start_date", "end_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    return df

def upsert_rule(row: dict) -> None:
    row = dict(row)
    row["updated_at"] = pd.Timestamp.utcnow().isoformat()
    supa().table(TABLE_RULES).upsert(row, on_conflict="id").execute()

def delete_rule(rule_id: str) -> None:
    supa().table(TABLE_RULES).delete().eq("id", rule_id).execute()

# -----------------------------
# DB helpers: Overrides
# -----------------------------
def load_override(class_name: str, year: int, month: int) -> pd.DataFrame | None:
    resp = (
        supa().table(TABLE_OVERRIDES)
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
    if "Date" in df2.columns:
        df2["Date"] = pd.to_datetime(df2["Date"], errors="coerce").dt.strftime("%Y-%m-%d")

    payload = {
        "class_name": class_name,
        "year": int(year),
        "month": int(month),
        "data": df2.to_dict(orient="records"),
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }
    supa().table(TABLE_OVERRIDES).upsert(payload, on_conflict="class_name,year,month").execute()

def delete_override(class_name: str, year: int, month: int) -> None:
    supa().table(TABLE_OVERRIDES).delete().eq("class_name", class_name).eq("year", int(year)).eq("month", int(month)).execute()

# -----------------------------
# Schedule generator (base from DB)
# -----------------------------
def build_base_schedule(rate: float, rules_df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    days_in_month = calendar.monthrange(year, month)[1]
    rows = []

    for d in range(1, days_in_month + 1):
        date = pd.Timestamp(year, month, d)
        day_name = date.day_name()

        for _, r in rules_df.iterrows():
            if r.get("weekday") != day_name:
                continue

            start = r.get("start_date")  # python date or NaT
            end = r.get("end_date")

            if pd.notna(start) and start and date.date() < start:
                continue
            if pd.notna(end) and end and date.date() > end:
                continue

            dur = float(r.get("duration_hours") or 0)
            rows.append({
                "Date": date,
                "Day": day_name,
                "Class Duration (hrs)": dur,
                "Rate": float(rate),
                "Fee": float(rate) * dur,
                "Note": r.get("note") or "",
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Date").reset_index(drop=True)
    return df

# -----------------------------
# App UI
# -----------------------------
st.title("Teaching Schedule")

tab_schedule, tab_manage = st.tabs(["Schedule", "Manage Classes"])

# -----------------------------
# Tab 1: Schedule
# -----------------------------
with tab_schedule:
    # Month-year selector (default previous month)
    today = pd.Timestamp.today()
    default_date = (today - pd.DateOffset(months=1)).replace(day=1)
    selected_date = st.date_input("Select month & year", value=default_date)

    year = selected_date.year
    month = selected_date.month
    st.caption(f"Period: {calendar.month_name[month]} {year}")

    classes_df = fetch_classes(active_only=True)

    if classes_df.empty:
        st.info("No active classes. Add classes in the Manage Classes tab.")
    else:
        # Optional CSS to bring buttons closer
        st.markdown(
            """
            <style>
            div.stButton > button { margin-top: 0.15rem; margin-bottom: 0.15rem; }
            </style>
            """,
            unsafe_allow_html=True,
        )

        grand_total = 0.0

        for _, c in classes_df.iterrows():
            class_id = c["id"]
            class_name = c["class_name"]
            rate = float(c["rate"])

            st.subheader(class_name)
            st.caption(f"Rate: {rate:,.0f}/hr")

            rules_df = fetch_rules_for_class(class_id)
            base_df = build_base_schedule(rate, rules_df, year, month)

            override_df = load_override(class_name, year, month)
            df_to_edit = override_df if override_df is not None else base_df

            if df_to_edit is None or df_to_edit.empty:
                st.write("No classes scheduled for this month.")
                continue

            # Editable schedule
            edited = st.data_editor(
                df_to_edit,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Date": st.column_config.DateColumn("Date"),
                    "Fee": st.column_config.NumberColumn("Fee"),
                },
                key=f"schedule_editor_{class_name}_{year}_{month}",
            )

            # Keep Day and Fee consistent (recommended)
            if "Date" in edited.columns:
                edited["Date"] = pd.to_datetime(edited["Date"], errors="coerce")
                edited["Day"] = edited["Date"].dt.day_name()

            if {"Rate", "Class Duration (hrs)"}.issubset(edited.columns):
                edited["Fee"] = (
                    pd.to_numeric(edited["Rate"], errors="coerce").fillna(0)
                    * pd.to_numeric(edited["Class Duration (hrs)"], errors="coerce").fillna(0)
                )

            total_fee = float(pd.to_numeric(edited.get("Fee", 0), errors="coerce").fillna(0).sum())
            grand_total += total_fee

            c1, c2, c3 = st.columns([1, 1, 3])
            with c1:
                if st.button("Save", key=f"save_{class_name}_{year}_{month}"):
                    save_override(class_name, year, month, edited)
                    st.success("Saved.")
            with c2:
                if st.button("Reset", key=f"reset_{class_name}_{year}_{month}"):
                    delete_override(class_name, year, month)
                    st.success("Reset to base schedule.")
            with c3:
                st.metric("Total fee (this class)", f"{total_fee:,.0f}")

            st.divider()

        st.metric("Grand total (all classes)", f"{grand_total:,.0f}")

# -----------------------------
# Tab 2: Manage Classes
# -----------------------------
with tab_manage:
    st.header("Manage Classes and Rules")

    if st.button("Refresh data", key="refresh_manage"):
        st.rerun()

    classes_all = fetch_classes(active_only=False)

    with st.expander("Add new class", expanded=False):
        with st.form("add_class"):
            new_name = st.text_input("Class name", placeholder="e.g., Stella")
            new_rate = st.number_input("Rate (per hour)", min_value=0.0, step=10.0, value=450.0)
            new_active = st.checkbox("Active", value=True)
            new_note = st.text_input("Note (optional)")
            create = st.form_submit_button("Create")

        if create:
            if not new_name.strip():
                st.error("Class name is required.")
            else:
                upsert_class({
                    "class_name": new_name.strip(),
                    "rate": float(new_rate),
                    "active": bool(new_active),
                    "note": new_note,
                })
                st.success("Created.")
                st.rerun()

    if classes_all.empty:
        st.info("No classes yet.")
        st.stop()

    name_to_id = dict(zip(classes_all["class_name"], classes_all["id"]))
    selected_name = st.selectbox("Select class", options=list(name_to_id.keys()))
    selected_id = name_to_id[selected_name]

    row = classes_all.loc[classes_all["id"] == selected_id].iloc[0]

    st.subheader("Class details")
    with st.form("edit_class"):
        edit_name = st.text_input("Class name", value=str(row["class_name"]))
        edit_rate = st.number_input("Rate (per hour)", min_value=0.0, step=10.0, value=float(row["rate"]))
        edit_active = st.checkbox("Active", value=bool(row["active"]))
        edit_note = st.text_input("Note", value="" if pd.isna(row.get("note")) else str(row.get("note")))
        a, b = st.columns(2)
        save = a.form_submit_button("Save")
        delete = b.form_submit_button("Delete class")

    if save:
        upsert_class({
            "id": selected_id,
            "class_name": edit_name.strip(),
            "rate": float(edit_rate),
            "active": bool(edit_active),
            "note": edit_note,
        })
        st.success("Saved.")
        st.rerun()

    if delete:
        delete_class(selected_id)  # cascades to rules
        st.success("Deleted.")
        st.rerun()

    st.subheader("Weekly rules")

    rules_df = fetch_rules_for_class(selected_id)
    if rules_df.empty:
        rules_df = pd.DataFrame(columns=["id","weekday","duration_hours","start_date","end_date","note"])

    editor_df = rules_df[["id","weekday","duration_hours","start_date","end_date","note"]].copy()

    edited_rules = st.data_editor(
        editor_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "id": st.column_config.TextColumn("Rule ID", disabled=True),
            "weekday": st.column_config.SelectboxColumn("Weekday", options=WEEKDAYS),
            "duration_hours": st.column_config.NumberColumn("Duration (hrs)", min_value=0.0, step=0.5),
            "start_date": st.column_config.DateColumn("Start date"),
            "end_date": st.column_config.DateColumn("End date"),
            "note": st.column_config.TextColumn("Note"),
        },
        key=f"rules_editor_{selected_id}",
    )

    c1, c2 = st.columns([1, 3])

    with c1:
        if st.button("Save rules", key="save_rules"):
            for _, r in edited_rules.iterrows():
                weekday = (r.get("weekday") or "").strip()
                if weekday not in WEEKDAYS:
                    continue

                payload = {
                    "class_id": selected_id,
                    "weekday": weekday,
                    "duration_hours": float(r.get("duration_hours") or 0),
                    "start_date": r.get("start_date"),
                    "end_date": r.get("end_date"),
                    "note": r.get("note") or "",
                }

                rid = r.get("id")
                if isinstance(rid, str) and rid.strip():
                    payload["id"] = rid.strip()

                upsert_rule(payload)

            st.success("Rules saved.")
            st.rerun()

    with c2:
        st.caption("To delete a rule: copy its Rule ID, then add a delete UI. If you want row-level delete, tell me and I’ll add it cleanly.")
