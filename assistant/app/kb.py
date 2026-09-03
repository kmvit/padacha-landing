"""База знаний ассистента — тонкая обёртка над снапшотом data/kb.json.

Снапшот собирается заранее скриптом scripts/export_kb.py: тарифы и вопросы —
из index.html лендинга, знание о продукте — из data/product/*.json. Здесь
файл только читается и перечитывается по команде, без похода в код и без
похода в сеть.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class KnowledgeBase:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.error(
                "Снапшот базы знаний не найден: %s — запустите `python -m scripts.export_kb`",
                self._path,
            )
            self._data = {}
        except json.JSONDecodeError:
            logger.exception("Снапшот базы знаний повреждён: %s", self._path)
            self._data = {}

    # перечитать после export_kb, не перезапуская процесс
    reload = load

    @property
    def generated_at(self) -> str:
        return self._data.get("собрано", "")

    @property
    def contact(self) -> str:
        return self._data.get("контакт", "")

    @property
    def tariffs(self) -> list[dict]:
        return self._data.get("тарифы", [])

    @property
    def faq(self) -> list[dict]:
        return self._data.get("частые_вопросы", [])

    @property
    def product_topics(self) -> list[dict]:
        return self._data.get("продукт", [])

    @property
    def policy(self) -> dict:
        return self._data.get("политика", {})

    def as_json(self) -> str:
        """Снапшот целиком — для системного промпта.

        Компактно (без отступов): это read-only контекст для модели, а не
        файл для человека — лишние пробелы просто едят токены.
        """
        return json.dumps(self._data, ensure_ascii=False, separators=(",", ":"))


kb = KnowledgeBase(settings.kb_path)
