from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from app.database.models import CalendarDay, PaySchedule, UserSettings, WorkSession
from app.services.payments import build_payment_forecast
from app.services.payroll import MonthAnalysis
from app.services.time_tracking import session_work_minutes, total_break_minutes
from app.utils.formatters import DAY_TYPE_NAMES, format_minutes, format_money, format_rate, month_title


def build_today_report(
    user: UserSettings,
    day: CalendarDay,
    sessions: list[WorkSession],
    now_local: datetime,
) -> str:
    # отчёт дня
    zone = ZoneInfo(user.timezone)
    active = next((item for item in sessions if item.ended_at_utc is None), None)
    worked = sum(session_work_minutes(item, now_local.astimezone()) for item in sessions)
    lines = [f"<b>📍 Сегодня, {now_local:%d.%m.%Y}</b>", ""]
    lines.append(f"Тип дня: {DAY_TYPE_NAMES.get(day.day_type, day.day_type)}")
    lines.append(f"Норма: {format_minutes(day.expected_minutes)}")
    lines.append(f"Отработано: {format_minutes(worked)}")
    if day.expected_minutes > 0:
        lines.append(f"Плановое начало: {user.work_start_time:%H:%M}")
    if active:
        start = active.started_at_utc.astimezone(zone)
        active_break = next((item for item in active.breaks if item.ended_at_utc is None), None)
        lines.append(f"Статус: {'перерыв' if active_break else 'работа'}")
        lines.append(f"Приход: {start:%H:%M}")
        remaining = max(0, day.expected_minutes - worked)
        lines.append(f"До нормы: {format_minutes(remaining)}")
    else:
        lines.append("Статус: смена закрыта" if sessions else "Статус: смена не начата")
    return "\n".join(lines)


def build_month_report(analysis: MonthAnalysis) -> str:
    # отчёт месяца
    lines = [f"<b>📊 {month_title(analysis.year, analysis.month)}</b>", ""]
    lines.extend(
        [
            f"Отработано: <b>{format_minutes(analysis.worked_minutes)}</b>",
            f"Норма на текущую дату: {format_minutes(analysis.elapsed_standard_minutes)}",
            f"Баланс: <b>{format_minutes(analysis.balance_minutes, signed=True)}</b>",
            f"Переработка: {format_minutes(analysis.overtime_minutes + analysis.special_minutes)}",
            f"Оплачиваемое отсутствие: {format_minutes(analysis.paid_absence_minutes)}",
            "",
            f"Заработано сейчас: <b>{format_money(analysis.accrued_income_cents)}</b>",
            f"Прогноз выплаты: <b>{format_money(analysis.forecast_income_cents)}</b>",
            f"Доход от переработки: {format_money(analysis.overtime_income_cents)}",
            f"Удержание за недоработку: {format_money(analysis.underwork_deduction_cents)}",
            f"Расчётная ставка: {format_rate(analysis.hourly_rate_cents)}",
            "",
            f"Цель: {format_money(analysis.target_cents)}",
        ]
    )
    if analysis.target_gap_cents <= 0:
        lines.append("✅ Цель достигнута")
    else:
        lines.append(f"Осталось: <b>{format_money(analysis.target_gap_cents)}</b>")
        lines.extend(build_goal_plan_lines(analysis))
    if analysis.open_sessions:
        lines.extend(["", "⚠️ Есть незакрытая смена. Прогноз изменяется в реальном времени."])
    return "\n".join(lines)


def build_goal_plan_lines(analysis: MonthAnalysis) -> list[str]:
    plan = analysis.goal_plan
    lines = ["", "<b>План достижения цели</b>"]
    if not plan.items:
        lines.append("Нет доступного рабочего времени для расчёта.")
        return lines
    if plan.weekday_minutes_total:
        weekday_count = sum(1 for item in plan.items if item.kind == "weekday")
        average = (plan.weekday_minutes_total + weekday_count - 1) // weekday_count
        lines.append(f"• будни: примерно {format_minutes(average)} × {weekday_count}")
    if plan.weekend_minutes_total:
        weekend_items = [item for item in plan.items if item.kind == "weekend"]
        weekend_text = ", ".join(
            f"{item.work_date:%d.%m} — {format_minutes(item.minutes)}" for item in weekend_items
        )
        lines.append(f"• выходные: {weekend_text}")
    if plan.achievable:
        lines.append("✅ Цель достижима при заданных ограничениях.")
    else:
        lines.append(f"⚠️ Не покрыто: {format_money(plan.uncovered_cents)}")
    return lines


def build_history_report(sessions: list[WorkSession], user: UserSettings) -> str:
    # отчёт истории
    zone = ZoneInfo(user.timezone)
    if not sessions:
        return "За выбранный период смен нет."
    lines = ["<b>🗓 История смен</b>", ""]
    for session in sessions:
        start = session.started_at_utc.astimezone(zone)
        end = session.ended_at_utc.astimezone(zone) if session.ended_at_utc else None
        end_text = end.strftime("%H:%M") if end else "…"
        work_text = format_minutes(session_work_minutes(session))
        break_text = format_minutes(total_break_minutes(session))
        lines.append(f"<b>{start:%d.%m}</b>  {start:%H:%M}–{end_text} · {work_text} · перерыв {break_text}")
    return "\n".join(lines)


def build_payment_report(
    schedules: list[PaySchedule],
    analysis: MonthAnalysis,
    now_local: datetime,
) -> str:
    # отчёт выплаты
    forecasts = build_payment_forecast(
        schedules,
        analysis.year,
        analysis.month,
        now_local.date(),
        analysis.overtime_income_cents,
    )
    lines = [f"<b>💳 Выплаты · {month_title(analysis.year, analysis.month)}</b>", ""]
    for item in forecasts:
        status = "получено" if item.is_received else "ожидается"
        suffix = " + переработка" if item.includes_overtime else ""
        lines.append(
            f"• {escape(item.title)}: <b>{format_money(item.amount_cents)}</b>{suffix}\n"
            f"  {item.payment_date:%d.%m.%Y} · {status}"
        )
    lines.extend(["", f"Общий прогноз: <b>{format_money(analysis.forecast_income_cents)}</b>"])
    return "\n".join(lines)


def build_week_report(analysis: MonthAnalysis, now_local: datetime) -> str:
    # отчёт недели
    week_days = {
        item.work_date: item
        for item in analysis.daily
        if item.work_date.isocalendar()[:2] == now_local.date().isocalendar()[:2]
    }
    worked = sum(item.worked_minutes for item in week_days.values())
    expected = sum(item.expected_minutes for item in week_days.values())
    return "\n".join(
        [
            "<b>📈 Недельный отчёт</b>",
            "",
            f"Отработано: {format_minutes(worked)}",
            f"Норма: {format_minutes(expected)}",
            f"Баланс: <b>{format_minutes(worked - expected, signed=True)}</b>",
            f"Прогноз месяца: {format_money(analysis.forecast_income_cents)}",
        ]
    )
