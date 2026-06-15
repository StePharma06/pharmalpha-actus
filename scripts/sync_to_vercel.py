#!/usr/bin/env python3
"""
Sync pharmalpha-actus content into pharmalpha-site/actus/ subfolder.

Used by GitHub Actions after the daily update job. Performs:
- Mirror copy of relevant files from source repo to target/actus/
- URL transforms (actus.pharmalpha.fr -> pharmalpha.fr/actus)
- Asset path transforms in articles.json (assets/ -> /actus/assets/)

Env:
  SOURCE_DIR  Path to checked-out pharmalpha-actus repo (default: ".")
  TARGET_DIR  Path to checked-out pharmalpha-site repo (required)
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

SOURCE = Path(os.environ.get("SOURCE_DIR", ".")).resolve()
TARGET_ROOT = Path(os.environ["TARGET_DIR"]).resolve()
TARGET = TARGET_ROOT / "actus"

SYNC_FILES = [
    "index.html",
    "archives.html",
    "dashboard.html",
    "cgu.html",
    "privacy.html",
    "articles.json",
    "caducee-pharmacien.png",
]
SYNC_DIRS = ["articles", "assets", "output"]

SKIP_NAMES = {
    "CNAME", "README.md", "demo.html", "email_template_preview.html",
    ".git", ".github", "scripts", "tiktok-renderer", "rss_feeds.json",
}

URL_OLD = "actus.pharmalpha.fr"
URL_NEW = "pharmalpha.fr/actus"

# Convert relative paths to /actus/-prefixed absolute paths.
# Required because vercel.json has trailingSlash:false: /actus/ is
# redirected to /actus, breaking relative resolution for assets/img.
RELATIVE_PATH_FIXES = [
    (re.compile(r'(\b(?:src|href)=)(["\'])(assets/)'), r'\1\2/actus/\3'),
    (re.compile(r'(\b(?:src|href)=)(["\'])(articles/)'), r'\1\2/actus/\3'),
    (re.compile(r'(image_url\s*:\s*)(["\'])(assets/)'), r'\1\2/actus/\3'),
    (re.compile(r'(fetch\()(["\'])(articles\.json)'), r'\1\2/actus/\3'),
    (re.compile(r'(fetch\()(["\'])(output/)'), r'\1\2/actus/\3'),
]


def transform_html(text: str) -> str:
    text = text.replace(f"https://{URL_OLD}", f"https://{URL_NEW}")
    text = text.replace(f"http://{URL_OLD}", f"https://{URL_NEW}")
    text = re.sub(rf"\b{re.escape(URL_OLD)}\b", URL_NEW, text)
    for pat, repl in RELATIVE_PATH_FIXES:
        text = pat.sub(repl, text)
    return text


def transform_articles_json(text: str) -> str:
    data = json.loads(text)
    # articles.json peut etre une liste directe ou un dict {"articles": [...]}
    arts = data if isinstance(data, list) else data.get("articles", [])
    for a in arts:
        img = a.get("image_url") or ""
        if img.startswith("assets/"):
            a["image_url"] = "/actus/" + img
    return json.dumps(data, ensure_ascii=False, indent=2)


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in {".html", ".htm"}:
        text = src.read_text(encoding="utf-8")
        dst.write_text(transform_html(text), encoding="utf-8")
    elif src.name == "articles.json":
        text = src.read_text(encoding="utf-8")
        dst.write_text(transform_articles_json(text), encoding="utf-8")
    else:
        shutil.copy2(src, dst)


def sync_dir(src_dir: Path, dst_dir: Path) -> int:
    n = 0
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_NAMES]
        for fn in files:
            if fn in SKIP_NAMES:
                continue
            sp = Path(root) / fn
            rel = sp.relative_to(src_dir)
            dp = dst_dir / rel
            copy_file(sp, dp)
            n += 1
    return n


def main():
    if not TARGET_ROOT.exists():
        print(f"ERROR: target dir does not exist: {TARGET_ROOT}", file=sys.stderr)
        sys.exit(1)
    TARGET.mkdir(parents=True, exist_ok=True)

    total = 0
    for fn in SYNC_FILES:
        src = SOURCE / fn
        if not src.exists():
            print(f"  skip (missing): {fn}")
            continue
        copy_file(src, TARGET / fn)
        total += 1
        print(f"  file: {fn}")

    for d in SYNC_DIRS:
        src = SOURCE / d
        if not src.exists():
            print(f"  skip (missing): {d}/")
            continue
        n = sync_dir(src, TARGET / d)
        total += n
        print(f"  dir : {d}/ ({n} files)")

    # Regenere sitemap-actus.xml depuis articles.json (TARGET_ROOT/sitemap-actus.xml)
    regenerate_sitemap_actus()

    print(f"\nSynced {total} files to {TARGET}")


def regenerate_sitemap_actus():
    """Regenere sitemap-actus.xml a la racine pharmalpha-site (depuis articles.json)."""
    articles_json = TARGET / "articles.json"
    sitemap_path = TARGET_ROOT / "sitemap-actus.xml"
    if not articles_json.exists():
        print("  skip sitemap-actus regen (articles.json missing)")
        return
    try:
        data = json.loads(articles_json.read_text(encoding="utf-8"))
        articles = data.get("articles", [])
        urls = []
        # Pages racine /actus
        urls.append(("https://pharmalpha.fr/actus", None, "daily", "0.9"))
        urls.append(("https://pharmalpha.fr/actus/archives.html", None, "daily", "0.7"))
        # Articles individuels
        for a in articles:
            aid = a.get("id", "")
            date = a.get("date", "")
            if aid:
                urls.append((f"https://pharmalpha.fr/actus/articles/{aid}.html", date, "monthly", "0.5"))
        # Build XML
        lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for url, lastmod, freq, prio in urls:
            lines.append("  <url>")
            lines.append(f"    <loc>{url}</loc>")
            if lastmod:
                lines.append(f"    <lastmod>{lastmod}</lastmod>")
            lines.append(f"    <changefreq>{freq}</changefreq>")
            lines.append(f"    <priority>{prio}</priority>")
            lines.append("  </url>")
        lines.append("</urlset>")
        sitemap_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  sitemap-actus.xml regenere : {len(urls)} URLs")
    except Exception as e:
        print(f"  ⚠️  sitemap-actus regen erreur : {e}")


if __name__ == "__main__":
    main()
