import os
from typing import List, Dict, Optional

from openai import AsyncOpenAI


class AiClientError(Exception):
    """Base error for AI client issues."""


class AiNotConfiguredError(AiClientError):
    """Raised when AI client is not configured (no API key / base URL)."""


# --- Low-level client configuration -------------------------------------------------

_api_key = (
    os.getenv("OPENROUTER_API_KEY")
    or os.getenv("VSELM_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
    or os.getenv("YANDEX_API_KEY")
)

if os.getenv("OPENROUTER_API_KEY"):
    _base_url = "https://openrouter.ai/api/v1"
elif os.getenv("VSELM_API_KEY"):
    _base_url = os.getenv("VSELM_BASE_URL", "https://api.vsellm.ru/v1")
elif os.getenv("GOOGLE_API_KEY"):
    _base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
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
if _api_key and _base_url:
    _client = AsyncOpenAI(
        api_key=_api_key,
        base_url=_base_url,
        timeout=120.0,  # Увеличен таймаут для бесплатных моделей
        default_headers=_default_headers or None,
    )
else:
    _client = None


def is_ai_configured() -> bool:
    """Return True if AI client is configured and ready."""

    return _client is not None


def _select_model(model_hint: Optional[str] = None) -> str:
    """
    Select model based on environment and provider.

    model_hint can be used to differentiate between long chat responses
    and короткие резюме, но сейчас это просто хинт на будущее.
    """

    # Явная переопределялка всегда имеет приоритет
    env_model = os.getenv("AI_MODEL")
    if env_model:
        return env_model

    # Поведение как в старом `main.py`
    if _base_url and "openrouter.ai" in _base_url:
        return "google/gemma-3-4b-it:free"
    if _base_url and "vsellm.ru" in _base_url:
        return "gpt-3.5-turbo"
    if _base_url and "google" in _base_url.lower():
        return "gemini-pro"

    # Дефолт для "обычного" OpenAI-совместимого клиента
    # (совпадает с прежним значением)
    return "gpt-3.5-turbo"


async def chat(
    messages: List[Dict[str, str]],
    model_hint: Optional[str] = None,
    *,
    max_tokens: int = 400,
    temperature: float = 0.4,
) -> str:
    """
    Выполнить чат-запрос к ИИ и вернуть текст ответа.

    Инкапсулирует:
    - проверку, что клиент сконфигурирован;
    - выбор модели под провайдера;
    - вызов AsyncOpenAI и вытаскивание текста из ответа.
    """

    if _client is None:
        raise AiNotConfiguredError("AI client is not configured")

    model = _select_model(model_hint)

    response = await _client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    content = response.choices[0].message.content or ""
    return content.strip()

