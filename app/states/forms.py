from aiogram.fsm.state import State, StatesGroup


class GoalStates(StatesGroup):
    custom_value = State()


class SettingsStates(StatesGroup):
    value = State()


class AddSessionStates(StatesGroup):
    date = State()
    start = State()
    end = State()
    break_minutes = State()


class EditSessionStates(StatesGroup):
    start = State()
    end = State()
    break_minutes = State()
