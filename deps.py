from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_session
from app.models import User
from app.security.init_data import TelegramInitDataError, validate_init_data


async def get_current_user(
    x_telegram_init_data: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    raw_init_data = x_telegram_init_data
    if not raw_init_data and authorization and authorization.lower().startswith("tma "):
        raw_init_data = authorization[4:].strip()
    if not raw_init_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram initData is required")

    try:
        telegram_user = validate_init_data(
            raw_init_data, settings.bot_token, settings.telegram_initdata_max_age
        )
    except TelegramInitDataError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = await session.scalar(select(User).where(User.telegram_id == telegram_user.telegram_id))
    if user is None:
        user = User(
            telegram_id=telegram_user.telegram_id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            role="admin" if telegram_user.telegram_id in settings.admin_ids else "user",
        )
        session.add(user)
    else:
        user.username = telegram_user.username
        user.first_name = telegram_user.first_name
        user.last_name = telegram_user.last_name
        if telegram_user.telegram_id in settings.admin_ids:
            user.role = "admin"
    await session.commit()
    return user


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role is required")
    return user


def get_bot(request: Request):
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Telegram bot is not ready")
    return bot

