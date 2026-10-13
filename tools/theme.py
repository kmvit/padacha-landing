#!/usr/bin/env python3
"""Переключает оформление сайта: «classic» — то, что на сайте сейчас,
«riso» — двухкрасочная печать по бежевой бумаге (см. theme-riso.css).

Сборки у сайта нет, поэтому тема — это одна строка <link> в <head> каждой
страницы. Разметку она не трогает: theme-riso.css подключается поверх
page.css и nav.css и переопределяет токены, шрифты и печатные детали.
Отсюда и обратимость — тема снимается тем же скриптом.

    python3 tools/theme.py            # какая тема стоит сейчас
    python3 tools/theme.py --set riso
    python3 tools/theme.py --set classic

Главную строкой стилей не переключить: у неё своя вёрстка под каждое
оформление. Поэтому для неё скрипт подменяет сам файл — текущая версия
хранится как home-classic.html, ризографическая правится в riso/index.html.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = '<link rel="stylesheet" href="/theme-riso.css">'
#: Главная: где лежит каждая версия и куда она ставится
HOME = ROOT / "index.html"
HOME_CLASSIC = ROOT / "home-classic.html"
HOME_RISO = ROOT / "riso" / "index.html"
#: Якорь, после которого вставляем строку темы.
ANCHOR = '<link rel="stylesheet" href="/nav.css">'
#: Признак страницы с общей вёрсткой. Главная подключает nav.css, но свёрстана
#: по-своему — наложение её бы только испортило, поэтому отбираем по page.css.
SHARED = '<link rel="stylesheet" href="/page.css">'


def pages() -> list[Path]:
    """Страницы с общей вёрсткой: только их тема переключает наложением."""
    found = [p for p in ROOT.rglob("index.html") if "/riso/" not in str(p)]
    found.append(ROOT / "404.html")
    return sorted(
        p for p in found
        if p.exists() and SHARED in (t := p.read_text(encoding="utf-8")) and ANCHOR in t
    )


def current(files: list[Path]) -> str:
    on = sum(1 for p in files if LINK in p.read_text(encoding="utf-8"))
    if on == 0:
        return "classic"
    if on == len(files):
        return "riso"
    return f"вразнобой ({on} из {len(files)} страниц в ризографе)"


def apply(files: list[Path], theme: str) -> int:
    changed = 0
    for page in files:
        text = page.read_text(encoding="utf-8")
        before = text
        # сначала всегда снимаем — так повторный запуск не плодит строки
        text = re.sub(r"\n[ \t]*" + re.escape(LINK), "", text)
        if theme == "riso":
            text = text.replace(ANCHOR, ANCHOR + "\n" + LINK, 1)
        if text != before:
            page.write_text(text, encoding="utf-8")
            changed += 1
    return changed


def home_theme() -> str:
    """Какая версия главной сейчас лежит в index.html.

    Сравниваем с исходниками, а не ищем слово в тексте: разметка у версий
    разная целиком, и любое ключевое слово рано или поздно переедет.
    """
    if not HOME.exists():
        return "нет файла"
    now = HOME.read_text(encoding="utf-8")
    if HOME_RISO.exists() and now == to_root(HOME_RISO.read_text(encoding="utf-8")):
        return "riso"
    if HOME_CLASSIC.exists() and now == HOME_CLASSIC.read_text(encoding="utf-8"):
        return "classic"
    return "правили вручную"


def to_root(html: str) -> str:
    """Пути черновика — относительные, чтобы riso/index.html открывался
    двойным кликом без сервера. В корне сайта такие пути неверны, поэтому
    при установке выпрямляем их здесь, а не ломаем исходник."""
    html = html.replace('src="img/', 'src="/riso/img/')
    html = re.sub(r'src="\.\./', 'src="/', html)
    html = html.replace('href="../nav.css"', 'href="/nav.css"')
    html = html.replace('src="../nav.js"', 'src="/nav.js"')
    return html


def switch_home(theme: str) -> str:
    """Подменяет index.html. Классическая версия сохраняется один раз —
    дальше правки в неё вносят через home-classic.html."""
    if theme == "riso":
        if not HOME_RISO.exists():
            return "ризо-версии главной нет — пропустил"
        if not HOME_CLASSIC.exists():
            HOME_CLASSIC.write_text(HOME.read_text(encoding="utf-8"), encoding="utf-8")
        HOME.write_text(to_root(HOME_RISO.read_text(encoding="utf-8")), encoding="utf-8")
        return "главная: ризограф (прежняя сохранена в home-classic.html)"
    if not HOME_CLASSIC.exists():
        return "главная: не трогал — home-classic.html не найден"
    HOME.write_text(HOME_CLASSIC.read_text(encoding="utf-8"), encoding="utf-8")
    return "главная: вернул прежнюю"


def main() -> None:
    ap = argparse.ArgumentParser(description="Оформление сайта: classic или riso")
    ap.add_argument("--set", dest="theme", choices=("classic", "riso"))
    args = ap.parse_args()

    files = pages()
    if not files:
        sys.exit("Не нашёл страниц с общей вёрсткой — проверьте tools/theme.py")

    if not args.theme:
        print(f"Тема сейчас: {current(files)} · страниц с общей вёрсткой: {len(files)}")
        print(f"Главная: {home_theme()}")
        return

    if args.theme == "riso" and not (ROOT / "theme-riso.css").exists():
        sys.exit("Нет theme-riso.css — включать нечего")

    changed = apply(files, args.theme)
    print(f"Тема: {args.theme} · изменено страниц: {changed} из {len(files)}")
    print(switch_home(args.theme))


if __name__ == "__main__":
    main()
