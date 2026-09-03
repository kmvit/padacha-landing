"""Агент «Падачи» поверх Yandex AI Studio.

Без инструментов: вся база знаний уже лежит в системном промпте целиком
(см. app/prompt.py) — снапшот умещается в несколько тысяч токенов, и
дозагрузка по частям добавила бы только новый способ ошибиться, а не
сэкономила бы что-то ощутимое. Из-за этого агент проще, чем у соседнего
ассистента ХАК ИТС: один запрос — один ответ, без цикла вызовов инструментов.
"""

from __future__ import annotations

import asyncio
import logging
import re

from yandex_ai_studio_sdk import AsyncAIStudio

from app.config import settings
from app.prompt import GREETING, load_prompt

logger = logging.getLogger(__name__)

__all__ = ["Agent", "build_sdk", "GREETING"]

#: Сколько раз повторить запрос при обрыве связи. Обрыв на пути к облаку —
#: обычное дело, а для посетителя это потерянная реплика посреди разговора.
#: Повторяем только сетевые ошибки: отказ по существу (неверная модель,
#: кончилась квота) вторая попытка не починит.
NETWORK_RETRIES = 2
RETRY_PAUSE_SECONDS = 1.0

#: Сколько сообщений диалога держим сверх системного промпта.
MAX_HISTORY = 24

#: Разметку модель просили не использовать, но подстраховаться дешевле, чем
#: показать посетителю «**склад**» или «[demo](https://…)» в сыром виде.
#: Дешёвая модель инструкцию про списки через дефис соблюдает не всегда —
#: маркер в начале строки срезаем отдельно, оставляя перенос строки.
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_MD_MARKS_RE = re.compile(r"[*_`#]{1,3}")
_MD_LIST_MARK_RE = re.compile(r"^\s*[-•*]\s+", re.MULTILINE)

_NETWORK_ERRORS = (
    "ReadError", "ConnectError", "ConnectTimeout", "ReadTimeout",
    "WriteError", "PoolTimeout", "RemoteProtocolError", "TimeoutException",
)


def _is_network_error(exc: Exception) -> bool:
    return type(exc).__name__ in _NETWORK_ERRORS


def clean_markup(text: str) -> str:
    text = _MD_LINK_RE.sub(lambda m: f"{m.group(1)} — {m.group(2)}", text)
    text = _MD_LIST_MARK_RE.sub("", text)
    text = _MD_MARKS_RE.sub("", text)
    return text.strip()


_sdk: AsyncAIStudio | None = None


def build_sdk() -> AsyncAIStudio:
    """Один SDK-клиент на процесс — создаётся один раз при первом обращении."""
    global _sdk
    if _sdk is None:
        settings.require_credentials()
        _sdk = AsyncAIStudio(folder_id=settings.folder_id, auth=settings.api_key)
    return _sdk


def _is_user_message(message) -> bool:
    return isinstance(message, dict) and message.get("role") == "user" and "text" in message


class Agent:
    """Один экземпляр = один диалог (хранит свою историю)."""

    def __init__(self) -> None:
        sdk = build_sdk()
        self._model = sdk.chat.completions(settings.llm_model).configure(
            # Консультант, который придумывает цены, хуже суховатого.
            temperature=0.2,
            max_tokens=800,
        )
        self._messages: list = [{"role": "system", "text": load_prompt()}]

    def _trim_history(self) -> None:
        if len(self._messages) <= MAX_HISTORY + 1:
            return
        tail = self._messages[-MAX_HISTORY:]
        while tail and not _is_user_message(tail[0]):
            tail.pop(0)
        self._messages = [self._messages[0], *tail]

    async def _run_with_retry(self):
        last: Exception | None = None
        for attempt in range(NETWORK_RETRIES + 1):
            try:
                return await self._model.run(self._messages)
            except Exception as exc:  # noqa: BLE001 — сетевые ловим по имени класса
                if not _is_network_error(exc) or attempt == NETWORK_RETRIES:
                    raise
                last = exc
                logger.warning(
                    "Обрыв связи с моделью (%s), повтор %d из %d",
                    type(exc).__name__, attempt + 1, NETWORK_RETRIES,
                )
                await asyncio.sleep(RETRY_PAUSE_SECONDS * (attempt + 1))
        raise last  # недостижимо, но пусть тип возврата будет честным

    async def ask(self, user_text: str) -> str:
        """Прогоняет реплику через модель и возвращает готовый ответ.

        Пустая строка — модель ничего не сказала; вызывающий код решает,
        что показать посетителю (см. server.py).
        """
        self._messages.append({"role": "user", "text": user_text})
        self._trim_history()

        result = await self._run_with_retry()
        self._messages.append(result)
        return clean_markup(result.text or "")
