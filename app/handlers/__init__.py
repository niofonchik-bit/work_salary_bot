from aiogram import Router

from app.handlers import analytics, common, goals, history, settings, work_time


def build_root_router() -> Router:
    router = Router(name="root")
    router.include_router(common.router)
    router.include_router(work_time.router)
    router.include_router(analytics.router)
    router.include_router(history.router)
    router.include_router(goals.router)
    router.include_router(settings.router)
    return router
