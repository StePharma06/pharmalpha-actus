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


def transform_html(text: str) -> str:
    text = text.replace(f"https://{URL_OLD}", f"https://{URL_NEW}")
    text = text.replace(f"http://{URL_OLD}", f"https://{URL_NEW}")
    text = re.sub(rf"\b{re.escape(URL_OLD)}\b", URL_NEW, text)
    return text


def transform_articles_json(text: str) -> str:
    data = json.loads(text)
    arts = data.get("articles", [])
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

    print(f"\nSynced {total} files to {TARGET}")


if __name__ == "__main__":
    main()
