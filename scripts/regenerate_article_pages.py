#!/usr/bin/env python3
"""
Regenerate all article stub HTML pages from articles.json.
Also patches orphan stubs (articles not in articles.json) using existing OG data.

Usage:
    python scripts/regenerate_article_pages.py

Two passes:
  1. Articles in articles.json  -> full rebuild via _build_article_page_html
  2. Orphan stubs (no JSON data) -> patch canonical + meta description + JSON-LD minimal
                                    using existing og:title / og:description

Marc SEO P0 - 2026-05-11
"""

import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent

sys.path.insert(0, str(SCRIPT_DIR))
from update_actus import _build_article_page_html


def patch_orphan_stub(path: Path, article_id: str) -> bool:
    """Patch a legacy stub that has no JSON data.

    Reads og:title and og:description from the existing file and injects:
    - canonical (pharmalpha.fr/actus)
    - meta description
    - minimal Article JSON-LD

    Returns True if patched, False if already has canonical (skip).
    """
    from bs4 import BeautifulSoup

    text = path.read_text(encoding="utf-8")

    # Already patched in a previous run
    if 'rel="canonical"' in text:
        return False

    soup = BeautifulSoup(text, "html.parser")
    head = soup.find("head")
    if not head:
        return False

    # Extract data from existing OG tags
    def og(prop):
        tag = soup.find("meta", property=prop)
        return tag.get("content", "") if tag else ""

    titre_raw = og("og:title")
    resume_raw = og("og:description")
    og_image = og("og:image")

    if not titre_raw:
        return False

    canonical_url = f"https://pharmalpha.fr/actus/articles/{article_id}.html"

    # meta description: resume truncated to 155 chars
    if resume_raw and len(resume_raw) > 155:
        meta_desc = resume_raw[:152] + "..."
    else:
        meta_desc = resume_raw

    # Extract date from article_id pattern: actu_YYYY_MM_DD_N or lsv_YYYY_MM_DD
    date_published = ""
    m = re.search(r"(\d{4})_(\d{2})_(\d{2})", article_id)
    if m:
        date_published = f"{m.group(1)}-{m.group(2)}-{m.group(3)}T06:00:00+02:00"

    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": titre_raw[:110],
        "description": resume_raw[:200] if resume_raw else "",
        "datePublished": date_published,
        "dateModified": date_published,
        "author": {
            "@type": "Person",
            "name": "Stephen Robert",
            "url": "https://pharmalpha.fr/stephen-robert",
            "jobTitle": "Docteur en Pharmacie",
            "sameAs": ["https://www.linkedin.com/in/stephen-robert-pharm/"]
        },
        "publisher": {
            "@type": "Organization",
            "name": "Pharm'Alpha",
            "url": "https://pharmalpha.fr",
            "logo": {
                "@type": "ImageObject",
                "url": "https://pharmalpha.fr/assets/logo-pharmalpha.png"
            }
        },
        "image": og_image,
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": canonical_url
        },
        "inLanguage": "fr-FR",
        "isPartOf": {
            "@type": "WebSite",
            "name": "Pharm'Actus",
            "url": "https://pharmalpha.fr/actus"
        }
    }
    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)

    # Insert canonical just after charset meta
    charset_tag = head.find("meta", attrs={"charset": True})
    insert_after = charset_tag if charset_tag else head

    # Build new tags as strings then insert via BeautifulSoup
    canonical_tag = soup.new_tag("link", rel="canonical", href=canonical_url)
    desc_tag = soup.new_tag("meta")
    desc_tag["name"] = "description"
    desc_tag["content"] = meta_desc
    schema_script = soup.new_tag("script", type="application/ld+json")
    schema_script.string = "\n" + schema_json + "\n"

    # og:url: update to point to pharmalpha.fr if still on actus.pharmalpha.fr
    og_url_tag = soup.find("meta", property="og:url")
    if og_url_tag:
        og_url_tag["content"] = canonical_url

    # Insert at end of head (before closing tag)
    head.append(canonical_tag)
    head.append(desc_tag)
    head.append(schema_script)

    # Add og:locale if missing
    if not soup.find("meta", property="og:locale"):
        locale_tag = soup.new_tag("meta")
        locale_tag["property"] = "og:locale"
        locale_tag["content"] = "fr_FR"
        head.append(locale_tag)

    # Add article:published_time if missing and we have a date
    if date_published and not soup.find("meta", property="article:published_time"):
        pub_tag = soup.new_tag("meta")
        pub_tag["property"] = "article:published_time"
        pub_tag["content"] = date_published
        head.append(pub_tag)

    # Add internal links footer to body if not present
    body = soup.find("body")
    if body and "pharmalpha.fr/formations" not in str(body):
        footer_html = (
            '<footer class="article-footer">'
            '<p>Article redige par <a href="https://pharmalpha.fr/stephen-robert">Stephen Robert, Docteur en Pharmacie</a>.</p>'
            '<p>Decouvrir <a href="https://pharmalpha.fr/formations">les formations Pharm\'Alpha</a>.</p>'
            "</footer>"
        )
        footer_soup = BeautifulSoup(footer_html, "html.parser")
        body.append(footer_soup)

    path.write_text(str(soup), encoding="utf-8")
    return True


def main() -> None:
    articles_json = ROOT_DIR / "articles.json"
    articles_dir = ROOT_DIR / "articles"

    if not articles_json.exists():
        print(f"[ERROR] articles.json not found at {articles_json}")
        sys.exit(1)

    with open(articles_json, encoding="utf-8") as f:
        data = json.load(f)

    articles = data.get("articles", [])
    if not articles:
        print("[ERROR] No articles found in articles.json")
        sys.exit(1)

    articles_dir.mkdir(exist_ok=True)

    # --- Pass 1: full rebuild for all articles in articles.json ---
    known_ids = set()
    rebuilt = 0
    skipped_no_id = 0

    for a in articles:
        article_id = a.get("id", "")
        if not article_id:
            skipped_no_id += 1
            continue

        known_ids.add(article_id)
        page_html = _build_article_page_html(
            article_id=article_id,
            titre_raw=a.get("titre", ""),
            resume_raw=a.get("resume", ""),
            image_url=a.get("image_url", ""),
            date_str=a.get("date", ""),
            categorie=a.get("categorie", ""),
        )
        page_path = articles_dir / f"{article_id}.html"
        page_path.write_text(page_html, encoding="utf-8")
        rebuilt += 1

    print(f"Pass 1 - Rebuilt {rebuilt} article pages from articles.json")
    if skipped_no_id:
        print(f"  Skipped {skipped_no_id} entries (missing id)")

    # --- Pass 2: patch orphan stubs ---
    all_stubs = [f[:-5] for f in os.listdir(articles_dir) if f.endswith(".html")]
    orphans = [s for s in all_stubs if s not in known_ids]

    patched = 0
    already_ok = 0
    patch_failed = 0

    for orphan_id in orphans:
        stub_path = articles_dir / f"{orphan_id}.html"
        try:
            result = patch_orphan_stub(stub_path, orphan_id)
            if result:
                patched += 1
            else:
                already_ok += 1
        except Exception as e:
            print(f"  [WARN] Failed to patch {orphan_id}.html: {e}")
            patch_failed += 1

    print(f"Pass 2 - Orphan stubs: {patched} patched, {already_ok} already had canonical, {patch_failed} failed")

    # --- Spot-check ---
    if articles:
        first_id = articles[0].get("id", "")
        check_path = articles_dir / f"{first_id}.html"
        if check_path.exists():
            content = check_path.read_text(encoding="utf-8")
            checks = [
                ("canonical", 'rel="canonical"'),
                ("meta description", 'name="description"'),
                ("JSON-LD schema", '"@type": "Article"'),
                ("og:locale", "og:locale"),
                ("article:published_time", "article:published_time"),
                ("internal links", "pharmalpha.fr/formations"),
            ]
            print(f"\nSpot-check on {first_id}.html:")
            all_ok = True
            for label, marker in checks:
                ok = marker in content
                status = "OK" if ok else "MISSING"
                print(f"  [{status}] {label}")
                if not ok:
                    all_ok = False
            if all_ok:
                print("  All SEO elements present.")
            else:
                print("  WARNING: some elements missing.")

    # Check one orphan
    if orphans and patched > 0:
        sample_orphan = orphans[0]
        check_path2 = articles_dir / f"{sample_orphan}.html"
        if check_path2.exists():
            content2 = check_path2.read_text(encoding="utf-8")
            has_canonical = 'rel="canonical"' in content2
            has_schema = '"@type": "Article"' in content2
            print(f"\nSpot-check orphan {sample_orphan}.html:")
            print(f"  [{'OK' if has_canonical else 'MISSING'}] canonical")
            print(f"  [{'OK' if has_schema else 'MISSING'}] JSON-LD schema")

    total = rebuilt + patched
    print(f"\nTotal: {total} pages updated ({rebuilt} full rebuild + {patched} orphan patches)")


if __name__ == "__main__":
    main()
