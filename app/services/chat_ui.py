from __future__ import annotations

from contextlib import suppress

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup


class ChatUiService:
    def __init__(self) -> None:
        # экран чата
        self._message_ids: dict[int, int] = {}

    async def show(
        self,
        event: Message | CallbackQuery,
        text: str,
        reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
        *,
        force_new: bool = False,
        delete_input: bool = True,
    ) -> Message | None:
        # сообщение интерфейса
        if isinstance(event, CallbackQuery):
            return await self._show_callback(event, text, reply_markup)

        message = event
        key = self._key(message)
        if delete_input:
            await self.delete(message)

        message_id = self._message_ids.get(key)
        if force_new and message_id is not None:
            with suppress(TelegramBadRequest, TelegramForbiddenError):
                await message.bot.delete_message(message.chat.id, message_id)
            self._message_ids.pop(key, None)
            message_id = None

        can_edit = isinstance(reply_markup, InlineKeyboardMarkup) or reply_markup is None
        if message_id is not None and can_edit and not force_new:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=message_id,
                    text=text,
                    reply_markup=reply_markup,
                )
                return None
            except TelegramBadRequest as error:
                if "message is not modified" in str(error).lower():
                    return None
                self._message_ids.pop(key, None)
            except TelegramForbiddenError:
                self._message_ids.pop(key, None)

        sent = await message.bot.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=reply_markup,
        )
        self._message_ids[key] = sent.message_id
        return sent

    async def delete(self, message: Message | None) -> None:
        # удаление сообщения
        if message is None:
            return
        key = self._key(message)
        if self._message_ids.get(key) == message.message_id:
            self._message_ids.pop(key, None)
        try:
            await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError):
            return

    def remember(self, message: Message) -> None:
        # идентификатор сообщения
        self._message_ids[self._key(message)] = message.message_id

    async def _show_callback(
        self,
        callback: CallbackQuery,
        text: str,
        reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None,
    ) -> Message | None:
        message = callback.message
        if not isinstance(message, Message):
            return None

        key = self._key(message)
        if isinstance(reply_markup, ReplyKeyboardMarkup):
            sent = await message.answer(text, reply_markup=reply_markup)
            self._message_ids[key] = sent.message_id
            return sent

        try:
            await message.edit_text(text, reply_markup=reply_markup)
            self._message_ids[key] = message.message_id
            return message
        except TelegramBadRequest as error:
            if "message is not modified" in str(error).lower():
                self._message_ids[key] = message.message_id
                return message

        sent = await message.answer(text, reply_markup=reply_markup)
        self._message_ids[key] = sent.message_id
        return sent

    @staticmethod
    def _key(message: Message) -> int:
        return message.chat.id
