from aiogram import Router

from app.handlers import analytics, calendar, common, export, history, payments, settings, work


def build_root_router() -> Router:
    # маршрутизатор приложения
    router = Router(name="root")
    router.include_router(common.router)
    router.include_router(work.router)
    router.include_router(analytics.router)
    router.include_router(history.router)
    router.include_router(calendar.router)
    router.include_router(payments.router)
    router.include_router(export.router)
    router.include_router(settings.router)
    return router
