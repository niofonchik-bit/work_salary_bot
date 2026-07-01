from app.keyboards.inline import SETTINGS_SECTIONS, settings_root_keyboard, settings_section_keyboard


def test_settings_root_is_compact() -> None:
    keyboard = settings_root_keyboard()
    assert sum(len(row) for row in keyboard.inline_keyboard) == 7
    assert max(len(row) for row in keyboard.inline_keyboard) <= 2


def test_settings_sections_are_compact() -> None:
    for section, entries in SETTINGS_SECTIONS.items():
        keyboard = settings_section_keyboard(section)
        button_count = sum(len(row) for row in keyboard.inline_keyboard)
        assert len(entries) <= 5
        assert button_count == len(entries) + 1
