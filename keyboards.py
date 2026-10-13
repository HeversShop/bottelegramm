from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


def mini_app_keyboard(webapp_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏆 Открыть турнирный центр",
                    web_app=WebAppInfo(url=webapp_url),
                )
            ]
        ]
    )

