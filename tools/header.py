#!/usr/bin/env python3
"""Раскладывает одинаковую шапку и ссылки подвала по всем страницам сайта.

Сборки у сайта нет, поэтому шапка лежит копией в каждом index.html. Править
её руками в двенадцати файлах — верный способ, что они разъедутся (так и было:
на главной в меню стояли якоря, на внутренних — страницы). Меню меняют здесь,
потом запускают:

    python3 tools/header.py

В шапке — только страницы. Разделы продукта собраны в выпадашку
«Возможности», форматы заведений — в «Форматы», чтобы верхний ряд
не разрастался с каждой новой страницей.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Разделы продукта: адрес, название, подпись в выпадашке
FEATURES = [
    ("/qr-menu/", "QR-меню", "Заказ и оплата с телефона гостя"),
    ("/ekran-kuhni/", "Экран кухни и бара", "Очереди станций и тайминги блюд"),
    ("/sklad/", "Склад и себестоимость", "Тех. карты, приход по фото, списания"),
    ("/personal/", "Персонал и зарплата", "Смены, оплата за результат, ведомость"),
    ("/oplata/", "Оплата, касса и бонусы", "Онлайн, смарт-касса, возвраты, бонусы гостям"),
]
# Форматы заведений = тарифы: без зала («Стойка») и с залом («Зал»).
# Отдельные страницы под каждый тип (фудтрак, пекарня, бар) заводить только
# под реальный спрос в поиске — иначе это копии одного текста.
FORMATS = [
    ("/dlya-kofejni/", "Точка без зала", "Кофейня, фудтрак, пекарня, окно выдачи, островок в ТЦ"),
    ("/dlya-kafe/", "Кафе с залом", "Кафе, бистро, ресторан, бар с посадкой"),
]
PAGES = [
    ("/sravnenie/", "Сравнение"),
    ("/#pricing", "Тарифы"),
    ("/blog/", "Статьи"),
]
DEMO = "https://demo.padacha.ru"

SUN = ('<svg class="sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/>'
       '<path d="M12 2.6v2.2M12 19.2v2.2M2.6 12h2.2M19.2 12h2.2M5.4 5.4l1.6 1.6M17 17l1.6 1.6M18.6 5.4L17 7M7 17l-1.6 1.6"/></svg>')
MOON = ('<svg class="moon" viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M20.5 14.6A8.6 8.6 0 0 1 9.4 3.5a8.6 8.6 0 1 0 11.1 11.1z"/></svg>')


def url_of(path: Path) -> str:
    rel = path.parent.relative_to(ROOT).as_posix()
    return "/" if rel == "." else f"/{rel}/"


def current(url: str, href: str) -> str:
    """Статьи блога подсвечивают «Статьи», остальные — только свою страницу."""
    hit = url == href or (href == "/blog/" and url.startswith("/blog/"))
    return ' aria-current="page"' if hit else ""


def drop(url: str, key: str, label: str, entries) -> str:
    here = " here" if any(url == href for href, _, _ in entries) else ""
    items = "\n".join(
        f'          <a href="{href}"{current(url, href)}><b>{name}</b><span>{note}</span></a>'
        for href, name, note in entries
    )
    return f"""      <div class="drop">
        <button class="drop-btn{here}" type="button" aria-expanded="false" aria-controls="{key}">{label} <svg viewBox="0 0 10 10" aria-hidden="true"><path d="M1.5 3.5 5 7l3.5-3.5"/></svg></button>
        <div class="drop-panel" id="{key}">
{items}
        </div>
      </div>"""


def header(url: str) -> str:
    pages = "\n".join(
        f'      <a href="{href}"{current(url, href)}>{name}</a>' for href, name in PAGES
    )
    return f"""<header>
  <div class="wrap nav">
    <a class="brand" href="/"><span class="dot" aria-hidden="true"></span>Падача</a>
    <nav class="menu" id="menu" aria-label="Разделы сайта">
{drop(url, "features", "Возможности", FEATURES)}
{drop(url, "formats", "Форматы", FORMATS)}
{pages}
      <a href="{DEMO}" target="_blank" rel="noreferrer">Демо <span class="ext" aria-hidden="true">↗</span></a>
    </nav>
    <button class="theme-btn" id="theme" type="button" aria-label="Переключить тему" title="Светлая или тёмная тема">
      {SUN}
      {MOON}
    </button>
    <a class="btn sm" href="#call">Подключить</a>
    <button class="burger" id="burger" type="button" aria-expanded="false" aria-controls="menu" aria-label="Открыть меню">
      <svg class="bars" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
      <svg class="x" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>
    </button>
  </div>
</header>"""


def footer_links() -> str:
    links = [("/", "Главная")] + [(h, n) for h, n, _ in FEATURES] + [
        *[(h, n) for h, n, _ in FORMATS], ("/sravnenie/", "Сравнение"), ("/blog/", "Статьи"),
    ]
    return "<span>" + " · ".join(f'<a href="{h}">{n}</a>' for h, n in links) + "</span>"


def main() -> None:
    for page in sorted(ROOT.glob("**/index.html")):
        if any(part in {"assistant", "pult", "direct", "node_modules", "tools"} for part in page.parts):
            continue
        src = page.read_text(encoding="utf-8")
        out, n = re.subn(r"<header>.*?</header>", header(url_of(page)), src, count=1, flags=re.S)
        if not n:
            print(f"пропущено, нет шапки: {page.relative_to(ROOT)}")
            continue
        # ссылки подвала — строка, где перечислены разделы
        out = re.sub(r'<span>(?:<a href="/">Главная</a> · )?<a href="/qr-menu/">.*?</span>', footer_links(), out, count=1)
        if "/nav.css" not in out:
            out = out.replace("</head>", '<link rel="stylesheet" href="/nav.css">\n</head>', 1)
        if "/nav.js" not in out:
            out = out.replace("</body>", '<script src="/nav.js" defer></script>\n</body>', 1)
        if out != src:
            page.write_text(out, encoding="utf-8")
            print(f"обновлено: {page.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
