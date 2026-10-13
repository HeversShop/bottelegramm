import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from app.security.init_data import validate_init_data, validate_login_widget


def test_webapp_init_data_is_validated() -> None:
    token = "123:ABC"
    payload = {
        "auth_date": str(int(time.time())),
        "query_id": "query",
        "user": json.dumps({"id": 42, "username": "captain", "first_name": "Captain"}),
    }
    data_check = "\n".join(f"{key}={value}" for key, value in sorted(payload.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    payload["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()

    user = validate_init_data(urlencode(payload), token, 60)
    assert user.telegram_id == 42
    assert user.username == "captain"


def test_login_widget_is_validated() -> None:
    token = "123:ABC"
    payload: dict[str, str | int] = {
        "id": 42,
        "auth_date": int(time.time()),
        "username": "captain",
        "first_name": "Captain",
    }
    data_check = "\n".join(f"{key}={value}" for key, value in sorted(payload.items()))
    secret = hashlib.sha256(token.encode()).digest()
    payload["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()

    user = validate_login_widget(payload, token, 60)
    assert user.telegram_id == 42

