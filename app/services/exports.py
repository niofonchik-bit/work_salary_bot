from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict
from zoneinfo import ZoneInfo

from app.database.models import CalendarDay, UserSettings, WorkSession
from app.services.time_tracking import session_work_minutes, total_break_minutes


def build_csv_export(sessions: list[WorkSession], user: UserSettings) -> bytes:
    # экспорт csv
    zone = ZoneInfo(user.timezone)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";")
    writer.writerow(["Дата", "Приход", "Уход", "Перерыв, мин", "Работа, мин", "Комментарий"])
    for session in sessions:
        start = session.started_at_utc.astimezone(zone)
        end = session.ended_at_utc.astimezone(zone) if session.ended_at_utc else None
        writer.writerow(
            [
                start.strftime("%d.%m.%Y"),
                start.strftime("%H:%M"),
                end.strftime("%H:%M") if end else "",
                total_break_minutes(session),
                session_work_minutes(session),
                session.note or "",
            ]
        )
    return stream.getvalue().encode("utf-8-sig")


def build_json_export(
    user: UserSettings,
    calendar_days: list[CalendarDay],
    sessions: list[WorkSession],
) -> bytes:
    # экспорт json
    payload = {
        "version": 1,
        "user": asdict(user),
        "calendar": [asdict(item) for item in calendar_days],
        "sessions": [asdict(item) for item in sessions],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
