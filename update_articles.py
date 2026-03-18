#!/usr/bin/env python3
"""
update_articles.py — Syncs published articles from Elfsight author page
into writing/index.html and index.html.

Run manually:  python3 update_articles.py
Dependencies:  pip install requests beautifulsoup4
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependencies. Run: pip install requests beautifulsoup4")
    sys.exit(1)

# ── Configuration ──────────────────────────────────────────────────────────────

SOURCES = [
    {
        "author_url": "https://elfsight.com/author/ivan-timofeev/",
        "publisher": "Elfsight",
        "article_pattern": r"https://elfsight\.com/blog/[^/?#]+/?$",
        "tag": "API",   # label shown in the tag chip
    },
]

ARTICLES_JSON = Path("articles.json")
WRITING_HTML  = Path("writing/index.html")
HOME_HTML     = Path("index.html")

MAX_WRITING   = 20   # max articles on /writing
MAX_HOME      = 4    # max cards on homepage

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; site-updater/1.0)"}

# ── Fetch & parse ──────────────────────────────────────────────────────────────

def fetch_article_urls(author_url, pattern):
    """Return all unique article URLs from an author page."""
    r = requests.get(author_url, timeout=20, headers=HEADERS)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    seen = []
    for a in soup.find_all("a", href=True):
        href = a["href"].split("?")[0].rstrip("/") + "/"
        if re.match(pattern, href) and href not in seen:
            seen.append(href)
    return seen


def fetch_article_meta(url):
    """Fetch title, description, and date from an individual article page."""
    r = requests.get(url, timeout=20, headers=HEADERS)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Title
    title = ""
    for sel in [
        lambda s: s.find("meta", property="og:title"),
        lambda s: s.find("title"),
        lambda s: s.find("h1"),
    ]:
        tag = sel(soup)
        if tag:
            title = tag.get("content", "") or tag.get_text()
            title = title.strip()
            if title:
                break

    # Description
    desc = ""
    for attr in [{"property": "og:description"}, {"name": "description"}]:
        tag = soup.find("meta", attrs=attr)
        if tag and tag.get("content", "").strip():
            desc = tag["content"].strip()
            break

    # Date
    date_str = ""
    tag = soup.find("meta", property="article:published_time")
    if tag and tag.get("content"):
        try:
            dt = datetime.fromisoformat(tag["content"].replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    if not date_str:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    data = data[0]
                raw = data.get("datePublished", "")
                if raw:
                    date_str = raw[:10]
                    break
            except Exception:
                pass

    return {"url": url, "title": title, "description": desc, "date": date_str}


# ── HTML generation ────────────────────────────────────────────────────────────

def fmt_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %Y")
    except Exception:
        return date_str


def render_featured_article(article, indent="                    "):
    date_iso  = article.get("date", "")
    date_disp = fmt_date(date_iso)
    title     = article["title"]
    url       = article["url"]
    desc      = article.get("description", "")
    tag       = article.get("tag", "API")
    return (
        f'{indent}<article class="featured-article">\n'
        f'{indent}    <div class="featured-article-meta">\n'
        f'{indent}        <span class="tag">{tag}</span>\n'
        f'{indent}        <span>&middot;</span>\n'
        f'{indent}        <time datetime="{date_iso}">{date_disp}</time>\n'
        f'{indent}    </div>\n'
        f'{indent}    <h3><a href="{url}">{title}</a></h3>\n'
        f'{indent}    <p class="featured-article-desc">{desc}</p>\n'
        f'{indent}</article>'
    )


def render_home_card(article, indent="                    "):
    title = article["title"]
    url   = article["url"]
    desc  = article.get("description", "")
    tag   = article.get("tag", "API")
    return (
        f'{indent}<a href="{url}" class="card">\n'
        f'{indent}    <div class="card-top">\n'
        f'{indent}        <span class="card-tag">{tag}</span>\n'
        f'{indent}        <span class="card-arrow">&rarr;</span>\n'
        f'{indent}    </div>\n'
        f'{indent}    <p class="card-title">{title}</p>\n'
        f'{indent}    <p class="card-desc">{desc}</p>\n'
        f'{indent}</a>'
    )


# ── File update ────────────────────────────────────────────────────────────────

def replace_between(html, start_marker, end_marker, new_content, closing_indent="                    "):
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL,
    )
    repl = f"{start_marker}\n{new_content}\n{closing_indent}{end_marker}"
    result, n = pattern.subn(repl, html)
    if n == 0:
        raise ValueError(f"Marker not found in HTML: {start_marker!r}")
    return result


def update_writing_page(all_articles):
    html = WRITING_HTML.read_text(encoding="utf-8")
    top = all_articles[:MAX_WRITING]
    blocks = "\n\n".join(render_featured_article(a) for a in top)
    html = replace_between(html, "<!-- ARTICLES:START -->", "<!-- ARTICLES:END -->", blocks)
    WRITING_HTML.write_text(html, encoding="utf-8")
    print(f"  writing/index.html updated ({len(top)} articles)")


def update_home_page(all_articles):
    html = HOME_HTML.read_text(encoding="utf-8")
    top = all_articles[:MAX_HOME]
    cards = "\n".join(render_home_card(a) for a in top)
    html = replace_between(html, "<!-- HOME-ARTICLES:START -->", "<!-- HOME-ARTICLES:END -->", cards)
    HOME_HTML.write_text(html, encoding="utf-8")
    print(f"  index.html updated ({len(top)} cards)")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    known = json.loads(ARTICLES_JSON.read_text()) if ARTICLES_JSON.exists() else {"articles": []}
    known_urls = {a["url"] for a in known["articles"]}

    new_articles = []

    for source in SOURCES:
        print(f"Fetching {source['author_url']} ...")
        try:
            found = fetch_article_urls(source["author_url"], source["article_pattern"])
        except Exception as e:
            print(f"  ERROR fetching author page: {e}")
            continue

        new_urls = [u for u in found if u not in known_urls]
        print(f"  {len(found)} total, {len(new_urls)} new")

        for url in new_urls:
            print(f"  Fetching metadata: {url}")
            try:
                meta = fetch_article_meta(url)
                meta["publisher"] = source["publisher"]
                meta["tag"] = source["tag"]
                new_articles.append(meta)
            except Exception as e:
                print(f"  WARNING: could not fetch {url}: {e}")

    if not new_articles:
        print("No new articles found. Nothing to update.")
        return

    all_articles = new_articles + known["articles"]

    known["articles"] = all_articles
    ARTICLES_JSON.write_text(json.dumps(known, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"articles.json saved ({len(all_articles)} total)")

    update_writing_page(all_articles)
    update_home_page(all_articles)

    print("Done.")


if __name__ == "__main__":
    main()
