#!/usr/bin/env python3
"""
Regenerate all article stub HTML pages from articles.json.
Also patches orphan stubs (articles not in articles.json) using existing OG data.

Usage:
    python scripts/regenerate_article_pages.py

Two passes:
  1. Articles in articles.json  -> full rebuild via _build_article_page_html
  2. Orphan stubs (no JSON data) -> patch canonical + noindex,follow + meta description + JSON-LD minimal
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


def _build_orphan_stub_html(article_id: str, titre_raw: str, resume_raw: str, og_image: str) -> str:
    """Build a clean HTML stub for an orphan article (no articles.json entry).

    Uses the same template as _build_article_page_html to ensure consistent,
    well-formed HTML across all stubs.
    """
    # Escape for HTML attributes
    titre = titre_raw.replace('"', "&quot;").replace("'", "&#39;")
    resume = resume_raw.replace('"', "&quot;").replace("'", "&#39;") if resume_raw else ""

    meta_desc_raw = resume
    if len(meta_desc_raw) > 155:
        meta_desc = meta_desc_raw[:152] + "..."
    else:
        meta_desc = meta_desc_raw

    # OG image: prefer article image, fallback to default
    if og_image:
        # Normalize: replace actus.pharmalpha.fr with pharmalpha.fr/actus (Vercel target)
        image_url = og_image.replace("https://actus.pharmalpha.fr", "https://pharmalpha.fr/actus")
    else:
        image_url = "https://pharmalpha.fr/assets/og-default-actus.png"

    canonical_url = f"https://pharmalpha.fr/actus/articles/{article_id}.html"

    # Date from article_id: actu_YYYY_MM_DD_N or lsv_YYYY_MM_DD
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
        "image": image_url,
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

    return f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titre} - Pharm'Actus</title>
<link rel="canonical" href="{canonical_url}" />
<meta name="robots" content="noindex, follow" />
<meta name="description" content="{meta_desc}" />
<meta property="og:type" content="article" />
<meta property="og:title" content="{titre}" />
<meta property="og:description" content="{meta_desc}" />
<meta property="og:url" content="{canonical_url}" />
<meta property="og:image" content="{image_url}" />
<meta property="og:locale" content="fr_FR" />
<meta property="og:site_name" content="Pharm'Actus" />
<meta property="article:published_time" content="{date_published}" />
<meta property="article:author" content="https://pharmalpha.fr/stephen-robert" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{titre}" />
<meta name="twitter:description" content="{meta_desc}" />
<meta name="twitter:image" content="{image_url}" />
<script type="application/ld+json">
{schema_json}
</script>
</head>
<body>
<article>
  <h1>{titre}</h1>
  <p class="article-lead">{resume}</p>
  <footer class="article-footer">
    <p>Article redige par <a href="https://pharmalpha.fr/stephen-robert">Stephen Robert, Docteur en Pharmacie</a>.</p>
    <p>Decouvrir <a href="https://pharmalpha.fr/formations">les formations Pharm'Alpha</a>.</p>
  </footer>
</article>
</body>
</html>'''


def patch_orphan_stub(path: Path, article_id: str) -> bool:
    """Rebuild a legacy orphan stub (no articles.json entry) using a clean template.

    Extracts og:title, og:description, og:image from the existing file,
    then rewrites the stub entirely with _build_orphan_stub_html.

    Always rewrites (idempotent). Returns True if written, False on missing data.
    """
    from bs4 import BeautifulSoup

    text = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(text, "html.parser")

    def og(prop):
        tag = soup.find("meta", property=prop)
        return tag.get("content", "").strip() if tag else ""

    titre_raw = og("og:title")
    resume_raw = og("og:description")
    og_image = og("og:image")

    if not titre_raw:
        return False

    html = _build_orphan_stub_html(article_id, titre_raw, resume_raw, og_image)
    path.write_text(html, encoding="utf-8")
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
            full_text_raw=a.get("full_text", ""),
            source_url=a.get("source_url", ""),
            source_name=a.get("source", ""),
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

    print(f"Pass 2 - Orphan stubs: {patched} rebuilt, {already_ok} skipped (no og:title), {patch_failed} failed")

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
