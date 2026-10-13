import json

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.bot.keyboards import mini_app_keyboard
from app.config import get_settings

router = Router(name="start")


@router.message(CommandStart())
async def command_start(message: Message) -> None:
    settings = get_settings()
    await message.answer(
        "Добро пожаловать в CS2 Tournament Center!\n\n"
        "Здесь можно зарегистрироваться на турнир, собрать команду и следить за сеткой.",
        reply_markup=mini_app_keyboard(settings.webapp_url),
    )


@router.message(Command("id"))
async def command_id(message: Message) -> None:
    if message.from_user:
        await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")


@router.message(F.web_app_data)
async def handle_web_app_data(message: Message) -> None:
    """Optional callback for Mini App sendData(). Main operations use the REST API."""
    raw_data = message.web_app_data.data
    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError:
        await message.answer("Получены некорректные данные Mini App.")
        return
    action = payload.get("action", "unknown")
    await message.answer(f"Данные Mini App получены. Действие: {action}")

