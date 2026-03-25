#!/usr/bin/env python3
"""
Pharm'Actus - Mise a jour quotidienne
Fetch RSS → Claude curate (ton Stephen) → Pexels photos → Le Saviez-Vous → Update index.html
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
import feedparser


def claude_create(client, **kwargs):
    """Call Claude API with retry on overload (529) or rate limit (429)."""
    for attempt in range(4):
        try:
            return client.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            if e.status_code in (429, 529) and attempt < 3:
                wait = 60 * (attempt + 1)  # 60s, 120s, 180s
                print(f"    [RETRY] Claude erreur {e.status_code}, attente {wait}s...")
                time.sleep(wait)
            else:
                raise


SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
INDEX_HTML = ROOT_DIR / "index.html"
FEEDS_JSON = SCRIPT_DIR / "rss_feeds.json"
ASSETS_DIR = ROOT_DIR / "assets"

MAX_ARTICLES_TOTAL = 50
MAX_AGE_DAYS = 7
NEW_ARTICLES_PER_RUN = 3


# ── RSS ──────────────────────────────────────────────────────────────

def fetch_rss_articles():
    """Fetch articles from all RSS feeds."""
    with open(FEEDS_JSON) as f:
        config = json.load(f)

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    articles = []

    for feed_cfg in config["feeds"]:
        try:
            feed = feedparser.parse(feed_cfg["url"])
            for entry in feed.entries[:15]:
                published = None
                for date_field in ("published_parsed", "updated_parsed"):
                    if hasattr(entry, date_field) and getattr(entry, date_field):
                        from time import mktime
                        published = datetime.fromtimestamp(
                            mktime(getattr(entry, date_field)), tz=timezone.utc
                        )
                        break
                if published and published < cutoff:
                    continue

                title = getattr(entry, "title", "").strip()
                summary = re.sub(r"<[^>]+>", "", getattr(entry, "summary", "").strip())[:500]
                link = getattr(entry, "link", "")

                if title:
                    articles.append({
                        "title": title,
                        "summary": summary,
                        "link": link,
                        "source": feed_cfg["name"],
                        "categorie": feed_cfg["categorie"],
                        "date": published.strftime("%Y-%m-%d") if published else datetime.now().strftime("%Y-%m-%d"),
                    })
        except Exception as e:
            print(f"  [WARN] Erreur feed {feed_cfg['name']}: {e}")

    # Garder les 30 plus recents pour ne pas surcharger Claude
    articles.sort(key=lambda a: a["date"], reverse=True)
    articles = articles[:30]
    print(f"  {len(articles)} articles RSS retenus (30 max)")
    return articles


# ── CLAUDE : curation des actus (ton Stephen) ───────────────────────

def curate_with_claude(raw_articles):
    """Select and rewrite the best articles with Stephen's personal tone."""
    client = anthropic.Anthropic()

    articles_text = "\n\n".join(
        f"[{i+1}] {a['title']}\nSource: {a['source']} | Cat: {a['categorie']} | Date: {a['date']}\nResume: {a['summary']}\nLien: {a['link']}"
        for i, a in enumerate(raw_articles)
    )

    today = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""Tu es Stephen, pharmacien consultant chez Pharm'Alpha et redacteur en chef de Pharm'Actus.

=== TON STYLE ===
- Tu parles comme un pote pharmacien qui briefe ses confreres entre deux clients
- Tutoiement naturel, ton decontracte mais expert
- Phrases courtes et percutantes. Une idee par phrase. Pas de blabla.
- Questions rhetoriques pour interpeller ("Et devinez quoi ?", "Ca te rappelle quelque chose ?")
- Un brin d'humour ou d'ironie quand le sujet s'y prete
- Accroche forte des la premiere phrase. Pas de "bonjour", pas de "chers confreres"
- Jargon metier sans vulgariser (substitution, marge, DP, ROSP, honoraires, DCI, AMM, LFSS, etc.)
- Tu assumes que tes lecteurs sont pharmaciens titulaires, adjoints ou preparateurs
- Conclus avec un impact concret : qu'est-ce que ca change au comptoir demain matin ?

=== PUBLIC ===
Pharmaciens d'officine en France (PAS le grand public)

=== ARTICLES DU JOUR ({today}) ===
{articles_text}

---

Selectionne les {NEW_ARTICLES_PER_RUN} articles les plus percutants pour des pharmaciens d'officine.

Criteres :
- Impact direct sur l'exercice officinal (reglementation, marges, missions, approvisionnement)
- Pertinence business/economique
- Reglementaire (LFSS, conventions, ROSP)
- Sante publique si impact comptoir (vaccins, depistages, alertes)
- Diversite des sujets

Pour chaque article, genere :
- "titre" : accrocheur, max 80 car, style direct de Stephen
- "resume" : 2-3 phrases percutantes, angle pharmacien
- "full_text" : 150-250 mots, 4-5 paragraphes separes par \\n\\n. Style Stephen : phrases courtes, chiffres concrets, impact officine, humour si pertinent. 1ere phrase = accroche forte.
- "categorie" : "pharma_france" | "pharma_monde" | "sante"
- "badge_label" : "Pharma France" | "Pharma Monde" | "Sante"
- "source" et "source_url"
- "image_keywords" : 2-3 mots EN ANGLAIS pour chercher une photo libre de droit (ex: "pharmacy shelves", "vaccine injection", "pills bottle")

JSON UNIQUEMENT :
[
  {{
    "titre": "...",
    "resume": "...",
    "full_text": "...",
    "categorie": "...",
    "badge_label": "...",
    "source": "...",
    "source_url": "...",
    "image_keywords": "...",
    "date": "{today}"
  }}
]"""

    response = claude_create(client,
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    json_match = re.search(r"\[[\s\S]*\]", text)
    if json_match:
        return json.loads(json_match.group())

    print("  [ERROR] Claude n'a pas retourne de JSON valide")
    return []


# ── CLAUDE : generation du Le Saviez-Vous ────────────────────────────

def generate_lsv_with_claude(existing_lsv_titles):
    """Generate a daily Le Saviez-Vous about pharmacy/health history."""
    client = anthropic.Anthropic()
    today = datetime.now().strftime("%Y-%m-%d")

    existing = "\n".join(f"- {t}" for t in existing_lsv_titles) if existing_lsv_titles else "(aucun)"

    prompt = f"""Tu es Stephen, pharmacien passionne d'histoire de la pharmacie et de la sante.
Tu rediges un "Le Saviez-Vous" quotidien pour Pharm'Actus.

=== TON STYLE ===
- Tu racontes comme si tu partageais une anecdote fascinante a un pote pharmacien
- Accroche percutante ("Tu savais que...", "Imagine un peu...", "Figure-toi que...")
- Anecdotes concretes : dates, noms, lieux, chiffres
- Un twist ou un fait surprenant au milieu du recit
- Conclusion qui fait le lien avec le quotidien au comptoir aujourd'hui
- Phrases courtes, rythmees, une idee par phrase
- Humour bienvenu, ton decontracte, tutoiement naturel

=== SUJETS POSSIBLES ===
- Histoire d'un medicament celebre (decouverte, molecule, anecdote)
- Inventions pharmaceutiques marquantes
- Pharmaciens celebres ou meconnus
- Evolution du metier a travers les ages
- Plantes medicinales et leur histoire
- Grandes epidemies et reponse pharmaceutique
- Reglementations historiques qui ont change le metier
- Anecdotes insolites de la pharmacopee mondiale

=== TITRES DEJA UTILISES (ne pas refaire) ===
{existing}

Genere UN SEUL "Le Saviez-Vous" original.

JSON UNIQUEMENT :
{{
  "titre": "Le saviez-vous ? [titre accrocheur, max 80 car]",
  "resume": "2-3 phrases de teaser percutantes",
  "full_text": "250-350 mots, 5-6 paragraphes separes par \\n\\n. Raconte l'histoire de facon captivante, style Stephen. Derniere phrase = lien avec aujourd'hui au comptoir.",
  "image_keywords": "2-3 mots EN ANGLAIS pour photo libre de droit",
  "date": "{today}"
}}"""

    response = claude_create(client,
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        lsv = json.loads(json_match.group())
        lsv["categorie"] = "lsv"
        lsv["badge_label"] = "Le Saviez-Vous"
        lsv["source"] = "Pharm'Alpha"
        lsv["source_url"] = ""
        return lsv

    print("  [ERROR] Claude n'a pas retourne de JSON valide pour le LSV")
    return None


# ── PEXELS : photos libres de droit ──────────────────────────────────

def search_pexels_photo(query):
    """Search Pexels for a free stock photo. Returns (download_url, photographer)."""
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        print("    [SKIP] PEXELS_API_KEY non definie")
        return "", ""

    encoded = urllib.parse.quote(query)
    url = f"https://api.pexels.com/v1/search?query={encoded}&per_page=1&orientation=landscape"
    req = urllib.request.Request(url, headers={"Authorization": api_key})

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            if data.get("photos"):
                photo = data["photos"][0]
                # landscape = 1200x627, parfait pour le web
                img_url = photo["src"]["landscape"]
                photographer = photo.get("photographer", "")
                return img_url, photographer
    except Exception as e:
        print(f"    [PEXELS-ERR] {e}")
    return "", ""


def download_photo(url, dest_path):
    """Download a photo to local file."""
    try:
        urllib.request.urlretrieve(url, str(dest_path))
        return True
    except Exception as e:
        print(f"    [DL-ERR] {e}")
        return False


# ── HTML : insertion des articles ─────────────────────────────────────

def get_existing_lsv_titles():
    """Extract existing LSV titles from index.html."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    return re.findall(r'titre:\s*"(Le saviez-vous[^"]*)"', html, re.IGNORECASE)


def update_index_html(new_articles):
    """Insert new articles into index.html ARTICLES array."""
    html = INDEX_HTML.read_text(encoding="utf-8")

    match = re.search(r"const ARTICLES = \[([\s\S]*?)\];", html)
    if not match:
        print("  [ERROR] ARTICLES array introuvable dans index.html")
        return False

    existing_block = match.group(1)
    existing_ids = set(re.findall(r'id:\s*"([^"]+)"', existing_block))

    today = datetime.now().strftime("%Y-%m-%d")
    ASSETS_DIR.mkdir(exist_ok=True)

    new_js_entries = []
    actu_idx = 0

    for a in new_articles:
        is_lsv = a.get("categorie") == "lsv"
        if is_lsv:
            article_id = f"lsv_{today.replace('-', '_')}"
        else:
            actu_idx += 1
            article_id = f"actu_{today.replace('-', '_')}_{actu_idx}"
        if article_id in existing_ids:
            article_id += "_b"

        def esc(s):
            return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

        vals = {
            "id": article_id,
            "date": today,
            "type": "lsv" if is_lsv else "actu",
            "categorie": a.get("categorie", "sante"),
            "titre": esc(a.get("titre", "")),
            "resume": esc(a.get("resume", "")),
            "full_text": esc(a.get("full_text", a.get("resume", ""))),
            "source": esc(a.get("source", "Pharm'Alpha")),
            "source_url": a.get("source_url", ""),
            "badge_label": a.get("badge_label", "Sante"),
        }

        # Photo Pexels
        img_url = ""
        img_keywords = a.get("image_keywords", "")
        print(f"  [{new_articles.index(a)+1}/{len(new_articles)}] {vals['titre'][:55]}...")
        if img_keywords:
            photo_url, photographer = search_pexels_photo(img_keywords)
            if photo_url:
                img_name = f"img_{article_id}.jpg"
                img_path = ASSETS_DIR / img_name
                if download_photo(photo_url, img_path):
                    img_url = f"assets/{img_name}"
                    print(f"    [IMG] {img_name} (Pexels{' - ' + photographer if photographer else ''})")

        entry = (
            '  {\n'
            f'    id: "{vals["id"]}",\n'
            f'    date: "{vals["date"]}",\n'
            f'    type: "{vals["type"]}",\n'
            f'    categorie: "{vals["categorie"]}",\n'
            f'    titre: "{vals["titre"]}",\n'
            f'    resume: "{vals["resume"]}",\n'
            f'    full_text: "{vals["full_text"]}",\n'
            f'    source: "{vals["source"]}",\n'
            f'    source_url: "{vals["source_url"]}",\n'
            '    tiktok_url: "",\n'
            f'    badge_label: "{vals["badge_label"]}",\n'
            f'    image_url: "{img_url}"\n'
            '  }'
        )
        new_js_entries.append(entry)

    if not new_js_entries:
        print("  Aucun nouvel article a ajouter")
        return False

    # Prepend (plus recents en premier)
    new_block = ",\n".join(new_js_entries)
    if existing_block.strip():
        updated_block = "\n" + new_block + ",\n" + existing_block.strip() + "\n"
    else:
        updated_block = "\n" + new_block + "\n"

    # Limiter le total
    all_entries = re.findall(r"\{[^}]+\}", updated_block, re.DOTALL)
    if len(all_entries) > MAX_ARTICLES_TOTAL:
        kept = all_entries[:MAX_ARTICLES_TOTAL]
        updated_block = "\n" + ",\n".join(kept) + "\n"

    updated_html = html[:match.start(1)] + updated_block + html[match.end(1):]
    INDEX_HTML.write_text(updated_html, encoding="utf-8")

    print(f"  {len(new_js_entries)} articles ajoutes a index.html")
    return True


# ── MAIN ──────────────────────────────────────────────────────────────

def main():
    print("=== Pharm'Actus - Mise a jour quotidienne ===")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # 1. Fetch RSS
    print("\n[1/4] Collecte des flux RSS...")
    raw_articles = fetch_rss_articles()
    if not raw_articles:
        print("  Aucun article RSS. Arret.")
        return

    # 2. Curate 3 actus
    print(f"\n[2/4] Curation via Claude ({len(raw_articles)} articles)...")
    curated = curate_with_claude(raw_articles)
    print(f"  {len(curated)} actus selectionnees")

    # 3. Generate 1 Le Saviez-Vous
    print("\n[3/4] Generation du Le Saviez-Vous...")
    existing_lsv = get_existing_lsv_titles()
    lsv = generate_lsv_with_claude(existing_lsv)
    if lsv:
        print(f"  LSV: {lsv.get('titre', '')[:60]}...")
        curated.append(lsv)
    else:
        print("  [WARN] Pas de LSV genere")

    if not curated:
        print("  Rien a publier. Arret.")
        return

    # 4. Photos Pexels + insertion HTML
    print("\n[4/4] Photos Pexels + mise a jour index.html...")
    updated = update_index_html(curated)

    if updated:
        print("\n=== Mise a jour terminee avec succes ===")
    else:
        print("\n=== Aucune mise a jour effectuee ===")


if __name__ == "__main__":
    main()
