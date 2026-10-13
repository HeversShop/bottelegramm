import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class TelegramInitDataError(ValueError):
    pass


@dataclass(slots=True)
class TelegramWebAppUser:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None


def validate_init_data(raw_init_data: str, bot_token: str, max_age: int) -> TelegramWebAppUser:
    if not raw_init_data:
        raise TelegramInitDataError("Telegram initData is required")

    pairs = dict(parse_qsl(raw_init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise TelegramInitDataError("initData hash is missing")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise TelegramInitDataError("initData hash is invalid")

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as exc:
        raise TelegramInitDataError("auth_date is invalid") from exc
    now = time.time()
    if auth_date <= 0 or auth_date > now + 60 or now - auth_date > max_age:
        raise TelegramInitDataError("initData has expired")

    try:
        user_payload = json.loads(pairs["user"])
        telegram_id = int(user_payload["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TelegramInitDataError("Telegram user payload is invalid") from exc

    return TelegramWebAppUser(
        telegram_id=telegram_id,
        username=user_payload.get("username"),
        first_name=user_payload.get("first_name"),
        last_name=user_payload.get("last_name"),
    )


def validate_login_widget(payload: dict[str, str | int], bot_token: str, max_age: int) -> TelegramWebAppUser:
    """Validate a Telegram Login Widget payload for an optional external web login."""
    data = {str(key): str(value) for key, value in payload.items() if key != "hash"}
    received_hash = str(payload.get("hash", ""))
    if not received_hash:
        raise TelegramInitDataError("Login Widget hash is missing")
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise TelegramInitDataError("Login Widget hash is invalid")
    try:
        telegram_id = int(data["id"])
        auth_date = int(data["auth_date"])
    except (KeyError, ValueError) as exc:
        raise TelegramInitDataError("Login Widget payload is invalid") from exc
    now = time.time()
    if auth_date <= 0 or auth_date > now + 60 or now - auth_date > max_age:
        raise TelegramInitDataError("Login Widget payload has expired")
    return TelegramWebAppUser(
        telegram_id=telegram_id,
        username=data.get("username"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
    )
