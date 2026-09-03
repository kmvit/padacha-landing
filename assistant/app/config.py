"""Настройки сервиса ассистента. Читаются из .env / переменных окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # Yandex AI Studio
    folder_id: str
    api_key: str
    llm_model: str

    # База знаний — снапшот продукта и сайта, собирается scripts/export_kb.py
    kb_path: Path

    # Ограничители: чат публичный и оплачивается по токенам
    session_ttl_seconds: int
    max_messages_per_session: int
    max_sessions_per_ip: int
    max_message_length: int
    daily_model_calls: int
    messages_per_ip_per_day: int
    messages_per_ip_per_minute: int
    min_seconds_between_messages: float

    # Секрет для /api/reload — тот же смысл, что у ХАК ИТС, но здесь дёргается
    # руками после export_kb, а не сигналом от Django (сайт статический).
    reload_token: str

    # Сервер
    host: str
    port: int
    allowed_origins: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Settings":
        kb_path = Path(os.getenv("KB_PATH", "data/kb.json"))
        if not kb_path.is_absolute():
            kb_path = BASE_DIR / kb_path

        return cls(
            folder_id=os.getenv("YC_FOLDER_ID", "").strip(),
            api_key=os.getenv("YC_API_KEY", "").strip(),
            # Инструментов у ассистента нет — «не зовёт function calling»
            # здесь не проблема, поэтому умолчание дешёвое. SDK сам дописывает
            # версию: «/latest» в имени превращается в «…/latest/latest».
            llm_model=os.getenv("LLM_MODEL", "yandexgpt-lite").strip().removesuffix("/latest"),
            kb_path=kb_path,
            session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "3600")),
            max_messages_per_session=int(os.getenv("MAX_MESSAGES_PER_SESSION", "40")),
            max_sessions_per_ip=int(os.getenv("MAX_SESSIONS_PER_IP", "5")),
            max_message_length=int(os.getenv("MAX_MESSAGE_LENGTH", "1000")),
            daily_model_calls=int(os.getenv("DAILY_MODEL_CALLS", "800")),
            messages_per_ip_per_day=int(os.getenv("MESSAGES_PER_IP_PER_DAY", "40")),
            messages_per_ip_per_minute=int(os.getenv("MESSAGES_PER_IP_PER_MINUTE", "8")),
            min_seconds_between_messages=float(os.getenv("MIN_SECONDS_BETWEEN_MESSAGES", "2")),
            reload_token=os.getenv("RELOAD_TOKEN", "").strip(),
            host=os.getenv("HOST", "127.0.0.1"),
            port=int(os.getenv("PORT", "8100")),
            allowed_origins=_list("ALLOWED_ORIGINS", "https://padacha.ru,https://www.padacha.ru"),
        )

    def require_credentials(self) -> None:
        missing = [
            name
            for name, value in (("YC_FOLDER_ID", self.folder_id), ("YC_API_KEY", self.api_key))
            if not value
        ]
        if missing:
            raise RuntimeError(
                f"Не заданы переменные окружения: {', '.join(missing)}. "
                "Скопируйте .env.example в .env и заполните доступы Yandex Cloud."
            )


settings = Settings.load()
