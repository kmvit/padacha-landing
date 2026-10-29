#!/usr/bin/env python3
"""Собирает статьи блога из исходников content/blog/<адрес>.md.

Статья в вёрстке — это четыреста строк, из которых девяносто процентов
одинаковая обвязка: шапка, счётчик, микроразметка, подвал. Писать её руками
под каждую статью — значит разъехаться в мелочах на третьей. Поэтому текст
лежит в Markdown (формат — content/blog/README.md), а скрипт делает три вещи:

  1. blog/<адрес>/index.html — страница в той же вёрстке, что и старые статьи;
  2. blog/index.html — карточка в списке и запись в микроразметке Blog;
  3. sitemap.xml — адрес с датой изменения.

    python3 tools/article.py                 # все статьи
    python3 tools/article.py fudkost lgota   # только эти
    python3 tools/article.py --preview slug  # статья из будущего,
                                                           # без списка и sitemap

Статья с published в будущем (`2026-10-25 09:00`, по Москве) не собирается:
её выпускает tools/publish.sh по cron на сервере, когда время наступит.

Нужен пакет markdown: локально `pip install markdown`, на сервере — окружение
/opt/padacha-build (его и зовёт tools/publish.sh).
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

try:
    import markdown as md
except ImportError:  # pragma: no cover
    sys.exit("нужен пакет markdown: pip install markdown (на сервере — /opt/padacha-build/bin/python)")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from header import footer_links, header  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "blog"
SITE = "https://padacha.ru"
OG_IMAGE = f"{SITE}/promo-poster.jpg"
METRIKA = 112273830
THEME_LINK = '<link rel="stylesheet" href="/theme-riso.css">'
MSK = ZoneInfo("Europe/Moscow")
REQUIRED = ("slug", "title", "description", "crumb", "lede", "published")

# Метки в blog/index.html, между которыми живут собранные карточки.
CARDS_START = "<!-- статьи из content/blog: начало -->"
CARDS_END = "<!-- статьи из content/blog: конец -->"


# ── разбор исходника ──────────────────────────────────────────────────────

def parse(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, flags=re.S)
    if not m:
        raise ValueError(f"{path.name}: нет шапки между ---")
    meta: dict = {}
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    missing = [k for k in REQUIRED if not meta.get(k)]
    if missing:
        raise ValueError(f"{path.name}: не заполнено {', '.join(missing)}")

    parts = re.split(r"^=== (faq|related)\s*$", m.group(2), flags=re.M)
    meta["body"] = parts[0].strip()
    sections = dict(zip(parts[1::2], parts[2::2]))

    meta["faq"] = []
    for block in re.split(r"^### ", sections.get("faq", ""), flags=re.M)[1:]:
        q, _, a = block.partition("\n")
        meta["faq"].append((q.strip(), a.strip()))

    meta["related"] = []
    for line in sections.get("related", "").splitlines():
        line = line.strip()
        if line.startswith("- "):
            href, name, note = (p.strip() for p in (line[2:].split("|") + ["", ""])[:3])
            meta["related"].append((href, name, note))

    # Время публикации: «2026-10-25» или «2026-10-25 09:00» (Москва). Пока оно
    # не наступило, статья не собирается — её выпускает cron на сервере.
    when = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}))?", meta["published"])
    if not when:
        raise ValueError(f"{path.name}: published — ГГГГ-ММ-ДД или ГГГГ-ММ-ДД ЧЧ:ММ")
    meta["published"] = when.group(1)
    meta["pub_at"] = datetime.fromisoformat(f"{when.group(1)}T{when.group(2) or '00:00'}")
    meta["published_iso"] = f"{when.group(1)}T{when.group(2)}:00+03:00" if when.group(2) else when.group(1)

    for field, limit in (("title", 70), ("description", 170)):
        if len(meta[field]) > limit:
            print(f"  ! {path.name}: {field} длиннее {limit} знаков ({len(meta[field])})")
    return meta


# ── Markdown → разметка сайта ─────────────────────────────────────────────

_MD = md.Markdown(
    extensions=["extra", "sane_lists", "smarty"],
    extension_configs={"smarty": {"substitutions": {"left-double-quote": "«", "right-double-quote": "»"}}},
    output_format="html",
)


def _callouts(out: str) -> str:
    """> [Метка] → <div class="callout"><span class="lbl">Метка</span>…"""
    def one(m: re.Match) -> str:
        inner = m.group(1).strip()
        label = re.match(r"<p>\[([^\]]+)\]\s*(?:<br\s*/?>|\n)?\s*", inner)
        if label:
            rest = inner[label.end():]
            inner = f'<span class="lbl">{label.group(1)}</span>\n<p>{rest}' if rest.strip() else \
                f'<span class="lbl">{label.group(1)}</span>'
            inner = inner.replace("<p></p>", "")
        # строки врезки — формулы и шаги расчёта, каждая с новой строки
        inner = re.sub(r"<p>(.*?)</p>", lambda p: "<p>" + re.sub(r"\n(?!$)", "<br>\n", p.group(1).strip()) + "</p>",
                       inner, flags=re.S)
        return f'<div class="callout">\n{inner}\n</div>'

    return re.sub(r"<blockquote>(.*?)</blockquote>", one, out, flags=re.S)


def _numeric_cells(out: str) -> str:
    def cell(m: re.Match) -> str:
        tag, attrs, inner = m.group(1), m.group(2), m.group(3)
        plain_text = re.sub(r"<[^>]+>", "", inner).strip()
        numeric = bool(plain_text) and re.fullmatch(r"[\d\s.,%₽×+\-−–—/()]+", plain_text)
        if numeric and "class=" not in attrs:
            return f'<{tag}{attrs} class="num">{inner}</{tag}>'
        return m.group(0)

    return re.sub(r"<(td|th)([^>]*)>(.*?)</\1>", cell, out, flags=re.S)


def render(text: str) -> str:
    _MD.reset()
    out = _MD.convert(text or "")
    out = _callouts(out)
    out = _numeric_cells(out)
    out = re.sub(r"<(/?)h1\b", r"<\1h2", out)
    out = re.sub(r'<th style="text-align: ?right;?">', '<th class="num">', out)
    out = re.sub(r'<td style="text-align: ?right;?">', '<td class="num">', out)
    return out


def plain(text: str) -> str:
    _MD.reset()
    out = _MD.convert(text or "")
    out = re.sub(r"<[^>]+>", " ", out)
    return html.unescape(re.sub(r"\s+", " ", out)).strip()


def one_line(text: str) -> str:
    """Заголовок без переносов <br> — для карточек и микроразметки."""
    return re.sub(r"\s*<br\s*/?>\s*", " ", text)


def indent(block: str, n: int) -> str:
    pad = " " * n
    return "\n".join(pad + line if line.strip() else "" for line in block.splitlines())


# ── страница статьи ───────────────────────────────────────────────────────

def theme_link() -> str:
    """Тема сайта — та, что сейчас стоит на списке статей (её ставит tools/theme.py)."""
    index = (ROOT / "blog" / "index.html").read_text(encoding="utf-8")
    return f"\n{THEME_LINK}" if THEME_LINK in index else ""


def jsonld(a: dict, url: str) -> str:
    org = {"@type": "Organization", "name": "Падача", "url": f"{SITE}/"}
    graph = [
        {
            "@type": "Article",
            "headline": a.get("headline") or one_line(a.get("h1") or a["title"]),
            "description": a["description"],
            "inLanguage": "ru",
            "datePublished": a["published_iso"],
            "dateModified": a.get("updated") or a["published_iso"],
            "image": a.get("image") or OG_IMAGE,
            "mainEntityOfPage": {"@type": "WebPage", "@id": url},
            "author": org,
            "publisher": org,
        },
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Падача", "item": f"{SITE}/"},
                {"@type": "ListItem", "position": 2, "name": "Статьи", "item": f"{SITE}/blog/"},
                {"@type": "ListItem", "position": 3, "name": a["crumb"], "item": url},
            ],
        },
    ]
    if a["faq"]:
        graph.append({
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": plain(ans)}}
                for q, ans in a["faq"]
            ],
        })
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=2)


def page(a: dict) -> str:
    slug = a["slug"]
    url = f"{SITE}/blog/{slug}/"
    e = html.escape
    h1 = a.get("h1") or e(a["title"])
    image = a.get("image") or OG_IMAGE

    faq = ""
    if a["faq"]:
        items = "\n".join(
            f"      <details>\n        <summary>{e(q)}</summary>\n{indent(render(ans), 8)}\n      </details>"
            for q, ans in a["faq"]
        )
        faq = f"""
  <section class="deep">
    <div class="wrap">
      <div class="head">
        <div class="lbl">Вопросы</div>
        <h2>{e(a.get("faq_title") or "Частые вопросы")}</h2>
      </div>
{items}
    </div>
  </section>
"""

    related = ""
    if a["related"]:
        links = "\n".join(
            f'        <a href="{e(h)}"><b>{e(n)}</b><span>{e(t)}</span></a>' for h, n, t in a["related"]
        )
        related = f"""
  <section>
    <div class="wrap">
      <div class="head">
        <div class="lbl">Читать дальше</div>
        <h2>Рядом по теме</h2>
      </div>
      <div class="more">
{links}
      </div>
    </div>
  </section>
"""

    call_title = a.get("call_title") or "Посмотрите, как это в работе"
    call_text = a.get("call_text") or ("Демо открыто круглосуточно: зайдите под любой ролью и потрогайте "
                                       "систему руками — или позвоните, проведём по вашему меню.")

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{e(a["description"])}">
<meta name="theme-color" content="#FF7A18">
<link rel="canonical" href="{url}">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta property="og:title" content="{e(a["title"])}">
<meta property="og:description" content="{e(a["description"])}">
<meta property="og:type" content="article">
<meta property="og:url" content="{url}">
<meta property="og:site_name" content="Падача">
<meta property="og:locale" content="ru_RU">
<meta property="og:image" content="{image}">
<meta property="article:published_time" content="{a["published_iso"]}">
<meta property="article:modified_time" content="{a.get("updated") or a["published_iso"]}">
<meta name="twitter:card" content="summary_large_image">
<title>{e(a["title"])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Unbounded:wght@400;600;800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<link rel="stylesheet" href="/page.css">
<!-- Yandex.Metrika counter -->
<script type="text/javascript">
    (function(m,e,t,r,i,k,a){{
        m[i]=m[i]||function(){{(m[i].a=m[i].a||[]).push(arguments)}};
        m[i].l=1*new Date();
        for (var j = 0; j < document.scripts.length; j++) {{if (document.scripts[j].src === r) {{ return; }}}}
        k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
    }})(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id={METRIKA}', 'ym');

    ym({METRIKA}, 'init', {{ssr:true, webvisor:true, clickmap:true, ecommerce:"dataLayer", referrer: document.referrer, url: location.href, accurateTrackBounce:true, trackLinks:true}});
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/{METRIKA}" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /Yandex.Metrika counter -->
<script type="application/ld+json">
{jsonld(a, url)}
</script>
<link rel="stylesheet" href="/nav.css">{theme_link()}
</head>
<body>
<script>
  (function () {{
    try {{
      var saved = localStorage.getItem("padacha-theme");
      if (saved === "light" || saved === "dark") document.documentElement.setAttribute("data-theme", saved);
    }} catch (e) {{}}
  }})();
</script>

{header(f"/blog/{slug}/")}

<main>
  <div class="page-hero">
    <div class="wrap">
      <div class="crumbs"><a href="/">Падача</a> → <a href="/blog/">Статьи</a> → {e(a["crumb"])}</div>
      <h1>{h1}</h1>
      <p class="lede">{e(a["lede"])}</p>
    </div>
  </div>

  <section>
    <div class="narrow prose">
{indent(render(a["body"]), 6)}
    </div>
  </section>
{faq}{related}
<div class="call" id="call">
    <div class="wrap">
      <div class="lbl">Заказ принят</div>
      <h2>{e(call_title)}</h2>
      <p>{e(call_text)}</p>
      <div class="contacts">
        <a class="btn" href="tel:+79943121222">Позвонить · +7 994 312-12-22</a>
        <a class="btn ghost" href="https://wa.me/79289557566" target="_blank" rel="noreferrer">WhatsApp</a>
        <a class="btn ghost" href="https://t.me/+79289557566" target="_blank" rel="noreferrer">Telegram</a>
        <a class="btn ghost" href="https://demo.padacha.ru" target="_blank" rel="noreferrer">Открыть демо</a>
      </div>
    </div>
  </div>
</main>

<footer>
  <div class="wrap foot">
    <span>© {date.today().year} Падача — система управления кафе</span>
    {footer_links()}
  </div>
</footer>
<script>
  (function () {{
    var btn = document.getElementById("theme");
    if (btn) btn.addEventListener("click", function () {{
      var root = document.documentElement;
      var dark = !(root.getAttribute("data-theme") === "light" ||
                   (!root.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: light)").matches));
      var next = dark ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {{ localStorage.setItem("padacha-theme", next); }} catch (e) {{}}
    }});
    document.addEventListener("click", function (e) {{
      var a = e.target.closest && e.target.closest("a[href]");
      if (!a || typeof ym !== "function") return;
      var h = a.getAttribute("href");
      var goal =
        h.indexOf("#call") !== -1 ? "click_connect" :
        h.indexOf("tel:") === 0 ? "click_phone" :
        /wa\\.me|t\\.me|max\\.ru/.test(h) ? "click_messenger" :
        h.indexOf("demo.padacha.ru") !== -1 ? "click_demo" : null;
      if (goal) ym({METRIKA}, "reachGoal", goal);
    }});
  }})();
</script>
<script src="/nav.js" defer></script>
</body>
</html>
"""


# ── список статей и sitemap ──────────────────────────────────────────────

def update_index(articles: list[dict]) -> None:
    path = ROOT / "blog" / "index.html"
    src = path.read_text(encoding="utf-8")
    e = html.escape
    fresh = sorted(articles, key=lambda a: (a["pub_at"], a["slug"]), reverse=True)

    cards = "\n".join(
        f"""        <a href="/blog/{a["slug"]}/">
          <div class="meta">{e(a.get("meta") or "Статья")}</div>
          <h2>{one_line(a.get("h1") or e(a["title"]))}</h2>
          <p>{e(a.get("card") or a["description"])}</p>
        </a>"""
        for a in fresh
    )
    block = f"{CARDS_START}\n{cards}\n        {CARDS_END}"
    if CARDS_START in src:
        src = re.sub(re.escape(CARDS_START) + r".*?" + re.escape(CARDS_END), lambda _: block, src, flags=re.S)
    else:
        src = src.replace('<div class="posts">', f'<div class="posts">\n        {block}', 1)

    # микроразметка Blog: собранные статьи — первыми, рукописные остаются
    m = re.search(r'(<script type="application/ld\+json">\s*)(\{.*?\})(\s*</script>)', src, flags=re.S)
    data = json.loads(m.group(2))
    blog = next(n for n in data["@graph"] if n.get("@type") == "Blog")
    ours = {f"{SITE}/blog/{a['slug']}/" for a in articles}
    kept = [p for p in blog.get("blogPost", []) if p.get("url") not in ours]
    blog["blogPost"] = [
        {
            "@type": "BlogPosting",
            "headline": one_line(a.get("h1") or a["title"]),
            "description": a.get("card") or a["description"],
            "url": f"{SITE}/blog/{a['slug']}/",
            "datePublished": a["published_iso"],
            "author": {"@type": "Organization", "name": "Падача"},
        }
        for a in fresh
    ] + kept
    src = src[:m.start(2)] + json.dumps(data, ensure_ascii=False, indent=2) + src[m.end(2):]
    path.write_text(src, encoding="utf-8")


def update_sitemap(articles: list[dict]) -> None:
    path = ROOT / "sitemap.xml"
    src = path.read_text(encoding="utf-8")
    newest = max(a.get("updated") or a["published"] for a in articles)
    for a in articles:
        loc = f"{SITE}/blog/{a['slug']}/"
        entry = (f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{a.get('updated') or a['published']}</lastmod>\n"
                 f"    <changefreq>monthly</changefreq>\n    <priority>0.8</priority>\n  </url>\n")
        pattern = rf"  <url>\n    <loc>{re.escape(loc)}</loc>.*?</url>\n"
        if re.search(pattern, src, flags=re.S):
            src = re.sub(pattern, lambda _: entry, src, flags=re.S)
        else:
            src = src.replace("</urlset>", entry + "</urlset>")
    src = re.sub(r"(<loc>https://padacha\.ru/blog/</loc>\s*<lastmod>)[^<]+", rf"\g<1>{newest}", src)
    path.write_text(src, encoding="utf-8")


def main(only: list[str], preview: bool = False) -> None:
    articles = [parse(p) for p in sorted(SRC.glob("*.md")) if p.name != "README.md"]
    if not articles:
        sys.exit("в content/blog нет статей")
    now = datetime.now(MSK).replace(tzinfo=None)
    due = [a for a in articles if a["pub_at"] <= now]
    for a in sorted((a for a in articles if a["pub_at"] > now), key=lambda a: a["pub_at"]):
        print(f"  запланировано: {a['slug']} — {a['pub_at']:%d.%m %H:%M}")
    for a in (articles if preview else due):
        if only and a["slug"] not in only:
            continue
        out = ROOT / "blog" / a["slug"] / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(a), encoding="utf-8")
        words = len(plain(a["body"]).split())
        print(f"собрано: blog/{a['slug']}/  ({words} слов, вопросов {len(a['faq'])})")
    if preview:
        print("предпросмотр: список статей и sitemap не тронуты")
        return
    # список и карта сайта — по всем вышедшим статьям, иначе потеряются соседи
    update_index(due)
    update_sitemap(due)
    print(f"обновлены blog/index.html и sitemap.xml: {len(due)} статей из content/blog")


if __name__ == "__main__":
    args = sys.argv[1:]
    preview = "--preview" in args
    args = [a for a in args if a != "--preview"]
    if any(arg.startswith("-") for arg in args):
        sys.exit(__doc__)
    main(args, preview)
