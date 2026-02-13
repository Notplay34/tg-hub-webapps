import asyncio
import os
from typing import List, Dict, Optional, Any

import httpx
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError


class AiClientError(Exception):
    """Base error for AI client issues."""


class AiNotConfiguredError(AiClientError):
    """Raised when AI client is not configured (no API key / base URL)."""


# --- Low-level client configuration -------------------------------------------------

# Yandex: Api-Key (секретный ключ) + folder id. Идентификатор ключа в запросах не используется.
_use_yandex = bool(
    os.getenv("YANDEX_API_KEY") and os.getenv("YANDEX_FOLDER_ID")
)

_api_key = (
    os.getenv("OPENROUTER_API_KEY")
    or os.getenv("VSELM_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
    or (os.getenv("YANDEX_API_KEY") if not _use_yandex else None)
)

if os.getenv("OPENROUTER_API_KEY"):
    _base_url = "https://openrouter.ai/api/v1"
elif os.getenv("VSELM_API_KEY"):
    _base_url = os.getenv("VSELM_BASE_URL", "https://api.vsellm.ru/v1")
elif os.getenv("GOOGLE_API_KEY"):
    _base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
elif _use_yandex:
    _base_url = "yandex"  # маркер: вызов через нативный API
else:
    _base_url = None

# Для OpenRouter нужны дополнительные заголовки
_default_headers: Dict[str, str] = {}
if os.getenv("OPENROUTER_API_KEY"):
    _default_headers = {
        "HTTP-Referer": "https://tghub.duckdns.org",
        "X-Title": "YouHub",
    }

_client: Optional[AsyncOpenAI]
if _api_key and _base_url and _base_url != "yandex":
    _client = AsyncOpenAI(
        api_key=_api_key,
        base_url=_base_url,
        timeout=120.0,  # Увеличен таймаут для бесплатных моделей
        default_headers=_default_headers or None,
    )
elif _use_yandex:
    _client = "yandex"  # type: ignore[assignment]
else:
    _client = None


def is_ai_configured() -> bool:
    """Return True if AI client is configured and ready."""

    return _client is not None


def _select_model(model_hint: Optional[str] = None) -> str:
    """
    Выбор модели по назначению.
    model_hint: chat (диалог), extract (команды), summary (сжатие истории).
    Можно задать AI_MODEL (общий) или AI_MODEL_CHAT, AI_MODEL_EXTRACT, AI_MODEL_SUMMARY.
    """
    hint_map = {
        "chat": os.getenv("AI_MODEL_CHAT") or os.getenv("AI_MODEL"),
        "extract": os.getenv("AI_MODEL_EXTRACT") or os.getenv("AI_MODEL"),
        "summary": os.getenv("AI_MODEL_SUMMARY") or os.getenv("AI_MODEL"),
    }
    if model_hint and hint_map.get(model_hint):
        return hint_map[model_hint]

    env_model = os.getenv("AI_MODEL")
    if env_model:
        return env_model

    if _base_url and "openrouter.ai" in _base_url:
        return "google/gemma-3-4b-it:free"
    if _base_url and "vsellm.ru" in _base_url:
        return "gpt-3.5-turbo"
    if _base_url and "google" in _base_url.lower():
        return "gemini-pro"
    if _base_url == "yandex":
        return os.getenv("AI_MODEL", "yandexgpt-lite/latest")
    return "gpt-3.5-turbo"


def _yandex_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Преобразовать сообщения в формат Yandex Foundation Models (role + text)."""
    out = []
    for m in messages:
        role = m.get("role", "user")
        if role == "tool":
            role = "assistant"
        content = m.get("content")
        if content is None:
            content = ""
        elif isinstance(content, list):
            content = " ".join(
                item.get("text", "") for item in content if item.get("type") == "text"
            )
        out.append({"role": role, "text": str(content)})
    return out


async def _chat_yandex(
    messages: List[Dict[str, Any]],
    model: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Запрос к Yandex Foundation Models API (Api-Key + x-folder-id)."""
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    folder_id = os.getenv("YANDEX_FOLDER_ID")
    api_key = os.getenv("YANDEX_API_KEY")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-Key {api_key}",
        "x-folder-id": folder_id,
        "x-data-logging-enabled": "false",
    }
    payload = {
        "modelUri": f"gpt://{folder_id}/{model}",
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": max_tokens,
        },
        "messages": _yandex_messages(messages),
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    alternatives = data.get("result", {}).get("alternatives", [])
    if not alternatives:
        return ""
    msg = alternatives[0].get("message", {})
    return (msg.get("text") or "").strip()


async def chat(
    messages: List[Dict[str, str]],
    model_hint: Optional[str] = None,
    *,
    max_tokens: int = 400,
    temperature: float = 0.4,
) -> str:
    """
    Выполнить чат-запрос к ИИ. Retry 1 раз при сетевых ошибках.
    """
    if _client is None:
        raise AiNotConfiguredError("AI client is not configured")

    model = _select_model(model_hint)
    last_error = None

    if _client == "yandex":
        for attempt in range(2):
            try:
                return await _chat_yandex(
                    messages, model, max_tokens=max_tokens, temperature=temperature
                )
            except (httpx.HTTPError, httpx.RequestError, ConnectionError) as e:
                last_error = e
                if attempt < 1:
                    await asyncio.sleep(1.0)
                    continue
                raise last_error
        assert last_error is not None
        raise last_error

    for attempt in range(2):
        try:
            response = await _client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = response.choices[0].message.content or ""
            return content.strip()
        except (APIConnectionError, APITimeoutError, ConnectionError) as e:
            last_error = e
            if attempt < 1:
                await asyncio.sleep(1.0)
                continue
            raise last_error
    assert last_error is not None
    raise last_error

