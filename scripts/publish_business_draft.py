#!/usr/bin/env python3
"""
Pharm'Actus - Publication d'un brouillon Business Officine
Lit un fichier draft dans DRAFTS/business/ et l'injecte dans index.html comme article

Usage:
  python scripts/publish_business_draft.py 2026-04-13.md
  python scripts/publish_business_draft.py  # prend le dernier brouillon

Ce script :
1. Parse le brouillon markdown
2. L'ajoute a index.html (categorie: business_officine)
3. Genere la page individuelle articles/business_YYYYMMDD.html
4. Deplace le brouillon vers DRAFTS/business/published/
"""

import json
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS_TZ = ZoneInfo("Europe/Paris")

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
INDEX_HTML = ROOT_DIR / "index.html"
ARTICLES_DIR = ROOT_DIR / "articles"
ASSETS_DIR = ROOT_DIR / "assets"
DRAFTS_DIR = ROOT_DIR / "DRAFTS" / "business"
PUBLISHED_DIR = DRAFTS_DIR / "published"


def parse_draft(path):
    """Parse a markdown draft and return a structured dict."""
    content = path.read_text(encoding="utf-8")

    # Extract frontmatter
    fm_match = re.match(r"^---\n([\s\S]*?)\n---\n([\s\S]*)$", content)
    if not fm_match:
        raise ValueError(f"Draft {path} has no frontmatter")

    frontmatter_text = fm_match.group(1)
    body = fm_match.group(2)

    frontmatter = {}
    for line in frontmatter_text.split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            frontmatter[k.strip()] = v.strip()

    # Extract title (first H1)
    titre_match = re.search(r"^# (.+)$", body, re.MULTILINE)
    titre = titre_match.group(1).strip() if titre_match else "Business Officine"

    # Extract sections
    def extract_section(name):
        pattern = rf"^## {re.escape(name)}\s*\n([\s\S]*?)(?=\n## |\Z)"
        m = re.search(pattern, body, re.MULTILINE)
        return m.group(1).strip() if m else ""

    chapo = extract_section("Chapo")
    contexte = extract_section("Contexte")
    analyse = extract_section("Analyse business")
    recommandations = extract_section("Recommandations actionnables")
    sources_raw = extract_section("Sources")

    # Parse sources (markdown links)
    sources = []
    for m in re.finditer(r"- \[([^\]]+)\]\(([^)]+)\)", sources_raw):
        sources.append({"nom": m.group(1), "url": m.group(2)})

    return {
        "titre": titre,
        "chapo": chapo,
        "contexte": contexte,
        "analyse": analyse,
        "recommandations": recommandations,
        "sources": sources,
        "date": frontmatter.get("date", datetime.now(PARIS_TZ).strftime("%Y-%m-%d")),
    }


def build_full_text(article):
    """Combine all sections into a single full_text for the site."""
    parts = []
    if article["chapo"]:
        parts.append(article["chapo"])
    if article["contexte"]:
        parts.append("**Contexte**\n\n" + article["contexte"])
    if article["analyse"]:
        parts.append("**Analyse business**\n\n" + article["analyse"])
    if article["recommandations"]:
        parts.append("**Recommandations actionnables**\n\n" + article["recommandations"])
    if article["sources"]:
        src_list = "\n".join(f"- {s['nom']}" for s in article["sources"])
        parts.append("**Sources**\n\n" + src_list)
    return "\n\n".join(parts)


def esc_js(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def insert_article_in_html(article):
    """Insert the business article into index.html ARTICLES array."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    match = re.search(r"const ARTICLES = \[([\s\S]*?)\];", html)
    if not match:
        raise RuntimeError("ARTICLES array introuvable dans index.html")

    date = article["date"]
    article_id = f"business_{date.replace('-', '_')}"

    existing_block = match.group(1)
    if f'id: "{article_id}"' in existing_block:
        print(f"  [SKIP] Article {article_id} deja present dans index.html")
        return article_id

    full_text = build_full_text(article)
    # Short resume for card (first sentence of chapo)
    resume = article["chapo"][:200]
    if len(article["chapo"]) > 200:
        resume += "..."

    # Tags for business article
    tags = ["business-officine", "analyse", "hebdo", "chiffres"]
    tags_js = "[" + ", ".join(f'"{t}"' for t in tags) + "]"

    # Sources: take first one for source/source_url
    source = article["sources"][0]["nom"] if article["sources"] else "Pharm'Alpha"
    source_url = article["sources"][0]["url"] if article["sources"] else ""

    entry = (
        '  {\n'
        f'    id: "{article_id}",\n'
        f'    date: "{date}",\n'
        f'    type: "business",\n'
        f'    categorie: "business_officine",\n'
        f'    titre: "{esc_js(article["titre"])}",\n'
        f'    resume: "{esc_js(resume)}",\n'
        f'    full_text: "{esc_js(full_text)}",\n'
        f'    source: "{esc_js(source)}",\n'
        f'    source_url: "{source_url}",\n'
        '    tiktok_url: "",\n'
        '    badge_label: "Business Officine",\n'
        '    image_url: "assets/stock/business_officine.jpg",\n'
        f'    tags: {tags_js}\n'
        '  }'
    )

    # Prepend (plus recent first)
    if existing_block.strip():
        updated_block = "\n" + entry + ",\n" + existing_block.strip() + "\n"
    else:
        updated_block = "\n" + entry + "\n"

    updated_html = html[:match.start(1)] + updated_block + html[match.end(1):]
    INDEX_HTML.write_text(updated_html, encoding="utf-8")
    print(f"  [HTML] Article inject dans index.html (id: {article_id})")
    return article_id


def generate_article_page(article_id, article):
    """Generate individual article page with og:tags for social sharing."""
    ARTICLES_DIR.mkdir(exist_ok=True)

    titre = article["titre"].replace('"', "&quot;")
    resume = article["chapo"].replace('"', "&quot;").replace("\n", " ")

    # Full text in HTML
    def md_to_html(text):
        text = text.replace("**", "")  # strip bold markers for simplicity
        paragraphs = text.split("\n\n")
        return "\n".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip())

    sources_html = ""
    if article["sources"]:
        sources_list = "\n".join(
            f'<li><a href="{s["url"]}" target="_blank" rel="noopener">{s["nom"]}</a></li>'
            for s in article["sources"]
        )
        sources_html = f"<h3>Sources</h3><ul>{sources_list}</ul>"

    page_html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titre} &mdash; Pharm'Actus Business</title>
<meta property="og:title" content="{titre}" />
<meta property="og:description" content="{resume}" />
<meta property="og:image" content="https://actus.pharmalpha.fr/assets/stock/business_officine.jpg" />
<meta property="og:url" content="https://actus.pharmalpha.fr/articles/{article_id}.html" />
<meta property="og:type" content="article" />
<meta property="og:site_name" content="Pharm'Actus" />
<meta http-equiv="refresh" content="0;url=https://actus.pharmalpha.fr/?a={article_id}" />
</head>
<body>
<p>Redirection vers <a href="https://actus.pharmalpha.fr/?a={article_id}">Pharm'Actus</a>...</p>
</body>
</html>"""

    page_path = ARTICLES_DIR / f"{article_id}.html"
    page_path.write_text(page_html, encoding="utf-8")
    print(f"  [PAGE] {page_path}")


def move_to_published(draft_path):
    """Move the draft to DRAFTS/business/published/ to mark it as used."""
    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    dest = PUBLISHED_DIR / draft_path.name
    shutil.move(str(draft_path), str(dest))
    print(f"  [ARCHIVE] Brouillon deplace vers {dest}")


def main():
    # Default: use most recent draft
    if len(sys.argv) > 1:
        draft_name = sys.argv[1]
        if not draft_name.endswith(".md"):
            draft_name += ".md"
        draft_path = DRAFTS_DIR / draft_name
    else:
        drafts = sorted(DRAFTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not drafts:
            print("[ERROR] Aucun brouillon trouve dans DRAFTS/business/")
            return
        draft_path = drafts[0]

    if not draft_path.exists():
        print(f"[ERROR] Brouillon introuvable : {draft_path}")
        return

    print(f"=== Publication : {draft_path.name} ===")

    print("\n[1/4] Parsing du brouillon...")
    article = parse_draft(draft_path)
    print(f"  Titre : {article['titre']}")
    print(f"  Date : {article['date']}")
    print(f"  Sources : {len(article['sources'])}")

    print("\n[2/4] Injection dans index.html...")
    article_id = insert_article_in_html(article)

    print("\n[3/4] Generation page individuelle...")
    generate_article_page(article_id, article)

    print("\n[4/4] Archivage du brouillon...")
    move_to_published(draft_path)

    print(f"\n=== Publie : {article_id} ===")
    print("N'oublie pas de commit + push les changements.")


if __name__ == "__main__":
    main()
