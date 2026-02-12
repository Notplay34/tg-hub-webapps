"""Валидация Telegram initData — извлечение user_id когда initDataUnsafe пуст (мобилка)."""
import json
from hashlib import sha256
from hmac import new as hmac_new
from typing import Optional
from urllib.parse import unquote


def get_user_id_from_init_data(init_data: str, bot_token: str) -> Optional[str]:
    """Проверяет подпись initData и возвращает user_id или None."""
    if not init_data or not bot_token:
        return None
    data_dict = {}
    hash_val = ""
    for chunk in init_data.split("&"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        if key == "hash":
            hash_val = value
            continue
        data_dict[key] = unquote(value)
    if not hash_val:
        return None
    data_check_str = "\n".join(f"{k}={data_dict[k]}" for k in sorted(data_dict.keys()))
    secret = hmac_new("WebAppData".encode(), bot_token.encode(), sha256).digest()
    computed = hmac_new(secret, data_check_str.encode(), sha256).hexdigest()
    if computed != hash_val:
        return None
    user_str = data_dict.get("user")
    if not user_str:
        return None
    try:
        user = json.loads(user_str)
        uid = user.get("id")
        return str(uid) if uid is not None else None
    except (json.JSONDecodeError, TypeError):
        return None
