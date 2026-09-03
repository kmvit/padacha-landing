#!/usr/bin/env python3
"""Сборка базы знаний ассистента в один снапшот data/kb.json.

Тарифы и частые вопросы берутся ПРЯМО из index.html — сайт остаётся
единственным источником цен. Дублировать их в файлах ассистента нельзя:
две копии неизбежно разъедутся, и ассистент назовёт клиенту цену,
которой на сайте нет.

Знание о работе продукта лежит в data/product/*.json и правится руками —
на сайте этих подробностей нет и не будет.

    python -m scripts.export_kb
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SITE = BASE.parent / "index.html"
PRODUCT = BASE / "data" / "product"
OUT = BASE / "data" / "kb.json"


def text(raw: str) -> str:
    """Разметку долой, пробелы схлопнуть.

    Обрезок в конце (`<section class="deep"`) убираем отдельно: срез страницы
    рвёт тег посередине, и обычное `<[^>]+>` его не ловит."""
    raw = re.sub(r"<[^>]*$", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def section(page: str, start: str, end: str) -> str:
    a = page.index(start)
    return page[a : page.index(end, a)]


def tariffs(page: str) -> dict:
    block = section(page, 'id="pricing"', 'id="faq"')
    plans = []
    for card in re.findall(r'<div class="card">(.*?)</div>\s*</div>', block, re.S):
        name = re.search(r"<h3>(.*?)</h3>", card, re.S)
        price = re.search(r'data-month="([^"]*)"\s+data-year="([^"]*)"', card)
        who = re.search(r'<div class="for">(.*?)</div>', card, re.S)
        if not (name and price):
            continue
        plans.append({
            "тариф": text(name.group(1)),
            "в_месяц": text(price.group(1)),
            "при_оплате_за_год": text(price.group(2)),
            "кому": text(who.group(1)) if who else "",
            "входит": [text(li) for li in re.findall(r"<li[^>]*>(.*?)</li>", card, re.S)],
        })
    # приписка под тарифами: пробный период, скидка сети, отсутствие доплат
    tail = text(block).split("Обсудить")[-1]
    return {"тарифы": plans, "условия": tail}


def faq(page: str) -> list[dict]:
    block = section(page, 'id="faq"', 'id="call"')
    return [
        {"вопрос": text(q), "ответ": text(a)}
        for q, a in re.findall(r"<summary>(.*?)</summary>(.*?)</details>", block, re.S)
    ]


def contact_email(page: str) -> str:
    """Единственный сейчас канал связи — берём из ссылки на сайте, а не
    вписываем руками: иначе рано или поздно разъедется, как цены."""
    m = re.search(r'mailto:([^"?]+)', page)
    return m.group(1) if m else ""


def main() -> None:
    page = SITE.read_text(encoding="utf-8")
    product = [
        json.loads(f.read_text(encoding="utf-8"))
        for f in sorted(PRODUCT.glob("[0-9]*.json"))
    ]
    kb = {
        "собрано": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "контакт": contact_email(page),
        "продукт": product,
        "политика": json.loads((PRODUCT / "policy.json").read_text(encoding="utf-8")),
        **tariffs(page),
        "частые_вопросы": faq(page),
    }
    OUT.write_text(json.dumps(kb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    size = len(json.dumps(kb, ensure_ascii=False))
    print(f"контакт: {kb['контакт'] or '(не найден)'}")
    print(f"тем о продукте: {len(product)}")
    print(f"тарифов: {len(kb['тарифы'])} — " + ", ".join(
        f"{p['тариф']} {p['в_месяц']}" for p in kb["тарифы"]))
    print(f"вопросов: {len(kb['частые_вопросы'])}")
    print(f"снапшот: {size} знаков (~{size // 3} токенов) → {OUT}")


if __name__ == "__main__":
    main()
