from aiogram import Dispatcher

from app.bot.handlers import admin, start


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(start.router)
    dispatcher.include_router(admin.router)
    return dispatcher

