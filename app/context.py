from __future__ import annotations

from dataclasses import dataclass

from app.config import Config
from app.database.session import Database
from app.repositories.audit import AuditRepository
from app.repositories.calendar import CalendarRepository
from app.repositories.payments import PaymentRepository
from app.repositories.reminders import ReminderRepository
from app.repositories.sessions import SessionRepository
from app.repositories.users import UserRepository
from app.use_cases.analysis import AnalysisUseCase
from app.use_cases.work_time import WorkTimeUseCase


@dataclass(slots=True)
class AppContext:
    config: Config
    database: Database
    users: UserRepository
    calendar: CalendarRepository
    sessions: SessionRepository
    reminders: ReminderRepository
    payments: PaymentRepository
    audit: AuditRepository
    analysis: AnalysisUseCase
    work_time: WorkTimeUseCase

    @classmethod
    def build(cls, config: Config, database: Database) -> AppContext:
        # контекст приложения
        users = UserRepository(database)
        calendar_repository = CalendarRepository(database)
        session_repository = SessionRepository(database)
        reminder_repository = ReminderRepository(database)
        payment_repository = PaymentRepository(database)
        audit_repository = AuditRepository(database)
        analysis = AnalysisUseCase(users, calendar_repository, session_repository)
        work_time = WorkTimeUseCase(session_repository, audit_repository)
        return cls(
            config=config,
            database=database,
            users=users,
            calendar=calendar_repository,
            sessions=session_repository,
            reminders=reminder_repository,
            payments=payment_repository,
            audit=audit_repository,
            analysis=analysis,
            work_time=work_time,
        )
