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
# исходник → {id узла: имя PNG}
SHOTS = {
    "mockups.html": {"shot-list": "menu-list.png", "shot-reels": "menu-reels.png", "shot-pay": "menu-pay.png"},
    "features.html": {"shot-kitchen": "kitchen.png", "shot-counter": "counter.png",
                      "shot-shifts": "shifts.png", "shot-receipt": "receipt.png",
                      "shot-stock": "stock.png", "shot-payroll": "payroll.png",
                      "shot-waiter": "waiter.png", "shot-table": "table.png",
                      "shot-compose-counter": "compose-counter.png", "shot-compose-waiter": "compose-waiter.png"},
}

with sync_playwright() as p:
    browser = p.chromium.launch()
    # x3 — чтобы картинка осталась резкой на retina и при уменьшении в вёрстке
    page = browser.new_context(device_scale_factor=3).new_page()
    for source, shots in SHOTS.items():
        # Не ждём «load»: Google Fonts иногда отвечают по полминуты и роняют goto.
        page.goto((HERE / source).as_uri(), wait_until="domcontentloaded")
        page.wait_for_function("document.fonts.status === 'loaded'", timeout=60000)
        page.wait_for_timeout(500)
        for node_id, filename in shots.items():
            page.locator(f"#{node_id}").screenshot(path=str(HERE / filename), omit_background=True)
            print("снято:", filename)
    browser.close()
