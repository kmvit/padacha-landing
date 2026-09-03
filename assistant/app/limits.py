"""Ограничители расхода: чат публичный, а каждая реплика стоит денег.

Два уровня:

  предохранитель  — дневной потолок вызовов модели на весь сервис. Единственное,
                    что даёт гарантию: сколько бы ни старались, больше этого
                    за сутки не потратится.
  темп и квота    — по IP-адресу, не по сессии: иначе кнопка «начать заново»
                    обнуляет счётчик и лимит не значит ничего.

Плюс фильтр мусора: «привет», «ааааа» и повтор реплики отвечаются заготовкой,
не трогая модель — пустой вопрос стоит ровно столько же, сколько осмысленный.

Всё в памяти процесса, как и диалоги (app/sessions.py). Перезапуск обнуляет
счётчики; для одного воркера это честный размен на отсутствие Redis.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from datetime import date


class DailyBudget:
    """Считает обращения к модели за календарные сутки."""

    def __init__(self, max_calls: int) -> None:
        self._max = max_calls
        self._day = date.today()
        self.calls = 0

    def _roll(self) -> None:
        today = date.today()
        if today != self._day:
            self._day, self.calls = today, 0

    @property
    def exhausted(self) -> bool:
        self._roll()
        return self._max > 0 and self.calls >= self._max

    def record(self) -> None:
        self._roll()
        self.calls += 1

    def stats(self) -> dict[str, int | str]:
        self._roll()
        return {"день": self._day.isoformat(), "вызовов_модели": self.calls, "потолок": self._max}


class IpLimiter:
    """Темп бережёт сервер и ломает автокликер. Дневная квота бережёт кошелёк."""

    def __init__(self, per_day: int, per_minute: int, min_interval: float) -> None:
        self._per_day = per_day
        self._per_minute = per_minute
        self._min_interval = min_interval
        self._day = date.today()
        self._today: dict[str, int] = defaultdict(int)
        self._recent: dict[str, deque[float]] = defaultdict(deque)
        self._last: dict[str, float] = {}

    def _roll(self) -> None:
        today = date.today()
        if today != self._day:
            self._day = today
            self._today.clear()

    def check_rate(self, ip: str) -> str | None:
        self._roll()
        now = time.monotonic()

        last = self._last.get(ip)
        if last is not None and now - last < self._min_interval:
            return "часто"

        window = self._recent[ip]
        while window and now - window[0] > 60:
            window.popleft()
        if self._per_minute and len(window) >= self._per_minute:
            return "минута"
        return None

    def check_quota(self, ip: str) -> str | None:
        self._roll()
        if self._per_day and self._today[ip] >= self._per_day:
            return "день"
        return None

    def record_rate(self, ip: str) -> None:
        now = time.monotonic()
        self._last[ip] = now
        self._recent[ip].append(now)

    def record_quota(self, ip: str) -> None:
        self._roll()
        self._today[ip] += 1

    def left_today(self, ip: str) -> int:
        self._roll()
        return max(0, self._per_day - self._today[ip]) if self._per_day else -1


_GREETING = {
    "привет", "приветик", "здравствуйте", "здравствуй", "добрый день",
    "добрый вечер", "доброе утро", "здарова", "хай", "ку", "hello", "hi", "hey",
}
_THANKS = {
    "спасибо", "спс", "благодарю", "пасиб", "пасибо", "ок", "окей", "ok",
    "понятно", "ясно", "угу", "ага", "хорошо", "пока", "до свидания",
}

#: Строка без единой буквы: цифры, знаки, эмодзи.
_NO_LETTERS = re.compile(r"^[^a-zA-Zа-яёА-ЯЁ]+$")
#: Одна буква, размноженная подряд: «ааааа», «))))», «!!!».
_REPEATED = re.compile(r"^(.)\1{3,}$")
#: Строка совсем без гласных — почти всегда набор случайных клавиш.
_VOWELS = re.compile(r"[аеёиоуыэюяaeiouy]", re.IGNORECASE)


def canned_reply(text: str, previous: str | None) -> str | None:
    """Готовый ответ на бессодержательную реплику, иначе None.

    Осторожно по построению: короткое «да» или «нет» посреди разговора —
    осмысленный ответ на вопрос ассистента, и глушить его нельзя. Поэтому
    ловим только то, на что модель всё равно ответила бы шаблоном.
    """
    stripped = text.strip()
    lowered = stripped.lower().rstrip("!.?,) ")

    if not stripped:
        return "Напишите вопрос словами — подскажу про меню, кухню, склад или деньги заведения."

    if previous and stripped == previous.strip():
        return "Вы прислали то же самое. Если ответ был не по делу — переформулируйте вопрос."

    if _NO_LETTERS.match(stripped) or _REPEATED.match(stripped):
        return "Не разобрал. Опишите словами — например «как работает склад» или «сколько стоит»."

    if len(stripped) <= 20 and not _VOWELS.search(stripped):
        return "Не разобрал. Опишите словами — например «как работает склад» или «сколько стоит»."

    if lowered in _GREETING:
        return "Здравствуйте. Спрашивайте про меню, кухню и бар, склад, смены или деньги заведения."

    if lowered in _THANKS:
        return "Пожалуйста. Если появятся ещё вопросы — я здесь."

    return None
