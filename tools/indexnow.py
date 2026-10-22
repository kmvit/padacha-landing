#!/usr/bin/env python3
"""Сообщает поисковикам о новых и изменённых страницах по протоколу IndexNow.

Яндекс берёт адрес в обход очереди, обычно в течение суток; тот же запрос
через api.indexnow.org получают Bing и другие участники протокола. Аккаунт
не нужен: право на сайт подтверждает файл-ключ в корне — <ключ>.txt.

    python3 tools/indexnow.py /blog/fudkost/ /sravnenie/   # эти адреса
    python3 tools/indexnow.py --since HEAD~1               # что поменялось в git

Запускать после выкатки на сервер: поисковик сразу придёт за страницей,
и она должна уже быть новой.
"""
from __future__ import annotations

import json
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = "padacha.ru"
ENDPOINTS = ["https://yandex.com/indexnow", "https://api.indexnow.org/indexnow"]


def key() -> str:
    found = [p for p in ROOT.glob("*.txt") if len(p.stem) == 32 and p.read_text().strip() == p.stem]
    if not found:
        sys.exit("нет файла-ключа <32 hex>.txt в корне сайта")
    return found[0].stem


def changed_since(rev: str) -> list[str]:
    """Страницы, чьи index.html поменялись с указанной ревизии."""
    out = subprocess.run(["git", "diff", "--name-only", rev, "--", "*.html"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    urls = []
    for f in out:
        if not f.endswith("index.html") or f.startswith(("riso/", "shots/")):
            continue
        rel = f[: -len("index.html")]
        urls.append("/" + rel)
    return urls


def main(args: list[str]) -> None:
    if not args or args[0] in ("-h", "--help"):
        sys.exit(__doc__)
    paths = changed_since(args[1]) if args[0] == "--since" else args
    if not paths:
        sys.exit("нечего отправлять")
    k = key()
    body = json.dumps({
        "host": HOST,
        "key": k,
        "keyLocation": f"https://{HOST}/{k}.txt",
        "urlList": [f"https://{HOST}{p}" for p in paths],
    }).encode()
    try:  # у Python с python.org на macOS нет системных сертификатов
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    ok = 0
    for url in ENDPOINTS:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                print(f"{url}: {r.status}")
                ok += r.status in (200, 202)
        except urllib.error.HTTPError as e:
            print(f"{url}: {e.code} {e.read().decode(errors='replace')[:200]}")
        except urllib.error.URLError as e:
            print(f"{url}: нет связи — {e.reason}")
    print(f"адресов: {len(paths)}, приняли: {ok} из {len(ENDPOINTS)}")


if __name__ == "__main__":
    main(sys.argv[1:])
