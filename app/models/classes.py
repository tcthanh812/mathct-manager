import json
from dataclasses import dataclass
from datetime import datetime, date
import pytz
from typing import Optional
# -----------------------------
# Data model
# -----------------------------
@dataclass
class Classes:
    class_id: str
    class_name: str
    rate: str
    start_date: str              # YYYY-MM-DD
    end_date: str                # YYYY-MM-DD
    week_day: str                # JSON list[str]
    duration_hours: str          # JSON list[float], aligned with week_day
    created_at_utc: str

    @staticmethod
    def create(
    *,
    class_id: str,
    class_name: str,
    rate: str,
    start_date: Optional[date],
    end_date: Optional[date],
    week_day: list[str],
    duration_hours: list[float],
) -> "Classes":
        now_utc = datetime.now(pytz.UTC).isoformat()
        return Classes(
            class_id=class_id,
            class_name=class_name.strip(),
            rate=rate.strip(),
            start_date=start_date.isoformat() if start_date else "",
            end_date=end_date.isoformat() if end_date else "",
            week_day=json.dumps(week_day, ensure_ascii=False),
            duration_hours=json.dumps(duration_hours, ensure_ascii=False),
            created_at_utc=now_utc,
        )