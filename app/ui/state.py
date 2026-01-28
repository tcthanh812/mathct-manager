# app/ui/state.py
import uuid
import streamlit as st

# Centralize keys to avoid typos across files
KEY_SCHEDULE_ROWS = "schedule_rows"
KEY_DO_RESET = "_do_reset"

KEY_CLASS_NAME = "class_name"
KEY_RATE = "rate"
KEY_START_DATE = "start_date"
KEY_END_DATE = "end_date"

def _new_schedule_row(day: str = "Mon", duration: float = 1.0) -> dict:
    return {"row_id": str(uuid.uuid4()), "day": day, "duration": float(duration)}

def init_state_if_missing() -> None:
    """Call at the top of the page before rendering widgets."""
    if KEY_SCHEDULE_ROWS not in st.session_state:
        st.session_state[KEY_SCHEDULE_ROWS] = [_new_schedule_row()]

def add_schedule_row() -> None:
    st.session_state[KEY_SCHEDULE_ROWS].append(_new_schedule_row())

def remove_schedule_row(row_id: str) -> None:
    st.session_state[KEY_SCHEDULE_ROWS] = [
        r for r in st.session_state[KEY_SCHEDULE_ROWS] if r["row_id"] != row_id
    ]
    if not st.session_state[KEY_SCHEDULE_ROWS]:
        st.session_state[KEY_SCHEDULE_ROWS] = [_new_schedule_row()]

def mark_reset() -> None:
    st.session_state[KEY_DO_RESET] = True

def apply_reset_if_marked() -> None:
    """
    If you use a 'reset on next run' pattern, call this at the very top
    of the page BEFORE creating widgets.
    """
    if st.session_state.get(KEY_DO_RESET):
        # Reset fields
        st.session_state[KEY_CLASS_NAME] = ""
        st.session_state[KEY_RATE] = ""
        st.session_state[KEY_START_DATE] = None
        st.session_state[KEY_END_DATE] = None
        st.session_state[KEY_SCHEDULE_ROWS] = [_new_schedule_row()]
        st.session_state[KEY_DO_RESET] = False
