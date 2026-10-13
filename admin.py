from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards import mini_app_keyboard
from app.config import get_settings

router = Router(name="admin")


@router.message(Command("admin"))
async def command_admin(message: Message) -> None:
    if not message.from_user or message.from_user.id not in get_settings().admin_ids:
        await message.answer("У вас нет доступа к админ-панели.")
        return
    await message.answer(
        "Админ-панель доступна в Mini App:",
        reply_markup=mini_app_keyboard(get_settings().webapp_url),
    )

