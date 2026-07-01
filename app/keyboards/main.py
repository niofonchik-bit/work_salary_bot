from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


class MainButtons:
    ARRIVE = "🟢 Пришёл"
    LEAVE = "🔴 Ушёл"
    ANALYTICS = "📊 Анализ"
    HISTORY = "🗓 История"
    GOAL = "🎯 Цель"
    SETTINGS = "⚙️ Настройки"


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MainButtons.ARRIVE), KeyboardButton(text=MainButtons.LEAVE)],
            [KeyboardButton(text=MainButtons.ANALYTICS), KeyboardButton(text=MainButtons.HISTORY)],
            [KeyboardButton(text=MainButtons.GOAL), KeyboardButton(text=MainButtons.SETTINGS)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие",
    )
