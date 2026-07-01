from aiogram.fsm.state import State, StatesGroup


class SettingForm(StatesGroup):
    value = State()


class ManualSessionForm(StatesGroup):
    value = State()


class SessionEditForm(StatesGroup):
    value = State()


class CalendarDateForm(StatesGroup):
    value = State()
