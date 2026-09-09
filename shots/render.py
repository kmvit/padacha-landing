#!/usr/bin/env python3
"""Рендер макетов телефона в PNG для лэндинга.

Снимаем не сайт, а собственную вёрстку mockups.html: так в кадре нет
подсказок-оверлеев, скелетонов загрузки и случайного состояния демо-стенда,
а размер и содержимое ровно те, что нужны блоку на сайте.

    python render.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SHOTS = {"shot-list": "menu-list.png", "shot-reels": "menu-reels.png", "shot-pay": "menu-pay.png"}

with sync_playwright() as p:
    browser = p.chromium.launch()
    # x3 — чтобы картинка осталась резкой на retina и при уменьшении в вёрстке
    page = browser.new_context(device_scale_factor=3).new_page()
    page.goto((HERE / "mockups.html").as_uri())
    page.wait_for_timeout(2500)  # веб-шрифты
    for node_id, filename in SHOTS.items():
        page.locator(f"#{node_id}").screenshot(path=str(HERE / filename), omit_background=True)
        print("снято:", filename)
    browser.close()
