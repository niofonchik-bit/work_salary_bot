from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.database.models import UserSettings, WorkSession
from app.services.salary_calculator import MonthAnalysis, ScheduleOption, summarize_sessions
from app.utils.formatters import (
    MONTH_NAMES,
    format_duration,
    format_money,
    format_rate,
)


def build_month_report(analysis: MonthAnalysis) -> str:
    lines = [
        f"<b>📊 Анализ за {MONTH_NAMES[analysis.month]} {analysis.year}</b>",
        "",
        f"Отработано: <b>{format_duration(analysis.totals.total_minutes)}</b>",
        f"Норма на текущую дату: {format_duration(analysis.elapsed_standard_minutes)}",
        f"Баланс времени: <b>{format_duration(analysis.balance_minutes, include_sign=True)}</b>",
        f"Норма за месяц: {format_duration(analysis.standard_minutes)}",
        "",
        f"Заработано по учёту: <b>{format_money(analysis.accrued_income_cents)}</b>",
        f"Переработка уже добавила: {format_money(analysis.overtime_income_cents)}",
        f"Прогноз выплаты: <b>{format_money(analysis.forecast_income_cents)}</b>",
        f"Расчётная ставка: {format_rate(analysis.hourly_rate_cents)}",
        "",
        f"Цель: <b>{format_money(analysis.target_cents)}</b>",
    ]

    if analysis.target_gap_cents <= 0:
        lines.extend(
            [
                "Цель уже достигнута по текущему прогнозу ✅",
            ]
        )
    elif analysis.hourly_rate_cents <= 0:
        lines.extend(
            [
                f"Осталось добрать: <b>{format_money(analysis.target_gap_cents)}</b>",
                "⚠️ Расчёт часов невозможен: ставка переработки равна нулю.",
            ]
        )
    else:
        lines.extend(
            [
                f"Осталось добрать: <b>{format_money(analysis.target_gap_cents)}</b>",
                f"Только в будни: примерно <b>{format_duration(analysis.weekday_minutes_to_target)}</b>",
                "",
                "<b>Варианты до конца месяца</b>",
            ]
        )
        for option in analysis.schedule_options:
            lines.append(_format_schedule_option(option))

    if analysis.totals.open_sessions:
        lines.extend(["", "⚠️ Активная смена включена в расчёт до текущего момента."])

    return "\n".join(lines)


def build_period_report(
    title: str,
    sessions: list[WorkSession],
    user: UserSettings,
    period_norm_minutes: int,
    now: datetime,
) -> str:
    totals = summarize_sessions(sessions, user.timezone, user.workday_minutes, now.astimezone(UTC))
    balance = totals.total_minutes - period_norm_minutes
    lines = [
        f"<b>{title}</b>",
        "",
        f"Отработано: <b>{format_duration(totals.total_minutes)}</b>",
        f"Норма: {format_duration(period_norm_minutes)}",
        f"Баланс: <b>{format_duration(balance, include_sign=True)}</b>",
        f"Переработка в будни: {format_duration(totals.weekday_overtime_minutes)}",
        f"Выходные: {format_duration(totals.weekend_minutes)}",
    ]
    if totals.open_sessions:
        lines.extend(["", "⚠️ Активная смена считается до текущего момента."])
    return "\n".join(lines)


def build_session_detail(session: WorkSession, timezone_name: str, now: datetime) -> str:
    zone = ZoneInfo(timezone_name)
    start = session.started_at_utc.astimezone(zone)
    end = session.ended_at_utc.astimezone(zone) if session.ended_at_utc else None
    effective_end = session.ended_at_utc or now.astimezone(session.started_at_utc.tzinfo)
    duration = max(0, int(round((effective_end - session.started_at_utc).total_seconds() / 60)))
    duration = max(0, duration - session.break_minutes)

    lines = [
        f"<b>🗓 Смена #{session.id}</b>",
        "",
        f"Дата: {start:%d.%m.%Y}",
        f"Приход: {start:%H:%M}",
        f"Уход: {end:%H:%M}" if end else "Уход: не зафиксирован",
        f"Перерыв: {format_duration(session.break_minutes)}",
        f"Итого: <b>{format_duration(duration)}</b>",
    ]
    return "\n".join(lines)


def get_week_bounds(day: date) -> tuple[date, date]:
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=7)


def _format_schedule_option(option: ScheduleOption) -> str:
    if option.requested_saturdays == 0:
        if option.remaining_weekdays <= 0:
            text = "• Без суббот: не осталось будних дней"
            if option.uncovered_cents > 0:
                text += f"; останется добрать {format_money(option.uncovered_cents)}"
            return text
        return (
            "• Без суббот: "
            f"+{format_duration(option.weekday_minutes_each)} в каждый из "
            f"{option.remaining_weekdays} оставшихся будних дней"
        )

    if option.saturday_count == 0:
        text = f"• До {option.requested_saturdays} суббот: доступных суббот больше нет"
        if option.weekday_minutes_each > 0:
            text += f", +{format_duration(option.weekday_minutes_each)} в будни"
        if option.uncovered_cents > 0:
            text += f"; останется {format_money(option.uncovered_cents)}"
        return text

    if option.saturday_count == 1:
        saturday_text = "1 суббота"
    elif option.saturday_count in (2, 3, 4):
        saturday_text = f"{option.saturday_count} субботы"
    else:
        saturday_text = f"{option.saturday_count} суббот"

    if option.saturday_count < option.requested_saturdays:
        saturday_text = f"{option.saturday_count} из {option.requested_saturdays} запланированных суббот"

    parts = [f"• {saturday_text} по {format_duration(option.saturday_minutes_each)}"]
    if option.weekday_minutes_each > 0 and option.remaining_weekdays > 0:
        parts.append(f"+ {format_duration(option.weekday_minutes_each)} в будни")
    else:
        parts.append("без дополнительных часов в будни")
    if option.uncovered_cents > 0:
        parts.append(f"останется добрать {format_money(option.uncovered_cents)}")
    return "; ".join(parts)
