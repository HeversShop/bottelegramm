import asyncio
from contextlib import asynccontextmanager

import uvicorn
from aiogram import Bot
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin_router, router
from app.bot.main import create_dispatcher
from app.config import get_settings
from app.database import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_db:
        await init_db()

    bot = Bot(token=settings.bot_token)
    dispatcher = create_dispatcher()
    app.state.bot = bot
    polling_task = asyncio.create_task(
        dispatcher.start_polling(bot, handle_signals=False, close_bot_session=False)
    )
    try:
        yield
    finally:
        await dispatcher.stop_polling()
        await polling_task
        await bot.session.close()


app = FastAPI(
    title="CS2 Tournament Center API",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-Telegram-Init-Data", "Authorization"],
)
app.include_router(router)
app.include_router(admin_router)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)

