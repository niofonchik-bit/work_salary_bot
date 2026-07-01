from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


class MainButtons:
    TODAY = "📍 Сегодня"
    ARRIVE = "🟢 Пришёл"
    LEAVE = "🔴 Ушёл"
    BREAK = "☕ Перерыв"
    ANALYTICS = "📊 Анализ"
    HISTORY = "🗓 История"
    CALENDAR = "📅 Календарь"
    PAYMENTS = "💳 Выплаты"
    EXPORT = "📤 Экспорт"
    SETTINGS = "⚙️ Настройки"


def main_keyboard() -> ReplyKeyboardMarkup:
    # клавиатура меню
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MainButtons.TODAY)],
            [KeyboardButton(text=MainButtons.ARRIVE), KeyboardButton(text=MainButtons.LEAVE)],
            [KeyboardButton(text=MainButtons.BREAK), KeyboardButton(text=MainButtons.ANALYTICS)],
            [KeyboardButton(text=MainButtons.HISTORY), KeyboardButton(text=MainButtons.CALENDAR)],
            [KeyboardButton(text=MainButtons.PAYMENTS), KeyboardButton(text=MainButtons.EXPORT)],
            [KeyboardButton(text=MainButtons.SETTINGS)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие",
    )
