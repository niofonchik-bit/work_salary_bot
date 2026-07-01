from enum import StrEnum


class DayType(StrEnum):
    WORKDAY = "workday"
    WEEKEND = "weekend"
    HOLIDAY = "holiday"
    VACATION = "vacation"
    SICK_LEAVE = "sick_leave"
    UNPAID_LEAVE = "unpaid_leave"
    DAY_OFF = "day_off"
    SHIFTED_WORKDAY = "shifted_workday"


class OvertimeRule(StrEnum):
    DAILY = "daily"
    MONTHLY = "monthly"
    BALANCE = "balance"


class RateBasis(StrEnum):
    TOTAL = "total"
    SALARY = "salary"
    CUSTOM = "custom"


class UnderworkMode(StrEnum):
    IGNORE = "ignore"
    DEDUCT = "deduct"


class PaymentDayRule(StrEnum):
    FIXED_DAY = "fixed_day"
    LAST_DAY = "last_day"
    LAST_WORKDAY = "last_workday"


class ReminderType(StrEnum):
    ARRIVAL = "arrival"
    DEPARTURE = "departure"
    OPEN_SHIFT = "open_shift"
    OPEN_BREAK = "open_break"
    WEEKLY_REPORT = "weekly_report"


class GeofenceEventType(StrEnum):
    ARRIVAL = "arrival"
    DEPARTURE = "departure"


class GeofenceEventStatus(StrEnum):
    RECORDED = "recorded"
    DUPLICATE = "duplicate"
    MERGED = "merged"


class PendingShiftStatus(StrEnum):
    WAITING_ARRIVAL = "waiting_arrival"
    WAITING_DEPARTURE = "waiting_departure"
    READY = "ready"
    ATTENTION = "attention"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
