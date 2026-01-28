CLASSES_TAB = "Classes"
CLASSES_HEADERS = [
    "class_id",
    "class_name",
    "rate",
    "start_date",
    "end_date",
    "week_day",
    "duration_hours",
    "created_at_utc",
]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# app/config.py

SESSIONS_TAB = "Sessions"

SESSIONS_HEADERS = [
    "session_id",
    "class_id",
    "class_name",
    "session_date",           # YYYY-MM-DD
    "weekday",                # Mon/Tue... 
    "duration",  # float (editable)
    "rate",                   # float (editable)
    "fee",                    # float (computed = actual_duration_hours * rate)
    "status",                 # editable (e.g., planned/done/cancel)
    "note",                   # editable
    "created_at_utc",
    "updated_at_utc",
]
