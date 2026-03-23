#!/usr/bin/env python3
"""
Pharm'Alpha - Mise a jour quotidienne des actualites
Fetch RSS feeds → Claude API curate & resume → Update index.html
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
import feedparser
from openai import OpenAI


SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
INDEX_HTML = ROOT_DIR / "index.html"
FEEDS_JSON = SCRIPT_DIR / "rss_feeds.json"
ASSETS_DIR = ROOT_DIR / "assets"

MAX_ARTICLES_TOTAL = 30  # Garder max 30 articles dans la page
MAX_AGE_DAYS = 7  # Chercher les articles des 7 derniers jours
NEW_ARTICLES_PER_RUN = 3  # Nombre d'articles a ajouter par jour


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
                # Parse date
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
                summary = getattr(entry, "summary", "").strip()
                link = getattr(entry, "link", "")

                # Nettoyer le HTML du summary
                summary = re.sub(r"<[^>]+>", "", summary)
                summary = summary[:500]

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

    print(f"  {len(articles)} articles RSS collectes")
    return articles


def curate_with_claude(raw_articles):
    """Use Claude API to select and curate the best articles."""
    client = anthropic.Anthropic()

    articles_text = "\n\n".join(
        f"[{i+1}] {a['title']}\nSource: {a['source']} | Categorie: {a['categorie']} | Date: {a['date']}\nResume: {a['summary']}\nLien: {a['link']}"
        for i, a in enumerate(raw_articles)
    )

    today = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""Tu es le redacteur de Pharm'Alpha, un media d'actualites pharma et sante.

Voici {len(raw_articles)} articles RSS collectes aujourd'hui ({today}) :

{articles_text}

---

Selectionne les {NEW_ARTICLES_PER_RUN} articles les plus importants et interessants pour des pharmaciens francais et le grand public.

Criteres de selection :
- Pertinence pour la pharmacie d'officine et la sante publique en France
- Nouveaute (pas de sujets deja largement couverts)
- Impact concret pour les pharmaciens ou les patients
- Diversite des sujets (evite 3 articles sur le meme theme)

Pour chaque article selectionne, genere :
- un titre accrocheur (max 80 caracteres)
- un resume de 2-3 phrases (informatif, factuel, engageant)
- un texte complet de 150-250 mots structure en PLUSIEURS PARAGRAPHES separes par \\n\\n (4-5 paragraphes). Style journalistique accessible, phrases courtes et percutantes, tutoiement OK. Chaque paragraphe = une idee. Utilise des chiffres, des faits concrets. Commence par une accroche forte. Termine par l'impact pour le pharmacien ou le patient.
- la categorie : "pharma_france", "pharma_monde" ou "sante"
- le badge_label correspondant : "Pharma France", "Pharma Monde" ou "Sante"

IMPORTANT pour full_text : le texte sera affiche en HTML avec des paragraphes <p>. Utilise \\n\\n pour separer chaque paragraphe. Ne fais PAS un bloc de texte continu.

Reponds UNIQUEMENT en JSON valide, format :
[
  {{
    "titre": "...",
    "resume": "...",
    "full_text": "...",
    "categorie": "pharma_france|pharma_monde|sante",
    "badge_label": "Pharma France|Pharma Monde|Sante",
    "source": "Nom de la source",
    "source_url": "URL de l'article original",
    "date": "{today}"
  }}
]"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Extraire le JSON (peut etre dans un bloc ```)
    json_match = re.search(r"\[[\s\S]*\]", text)
    if json_match:
        return json.loads(json_match.group())

    print("  [ERROR] Claude n'a pas retourne de JSON valide")
    return []


CAT_STYLE = {
    "pharma_france": "French pharmacy, blue white red tones",
    "pharma_monde": "global pharmaceutical, blue tones, world map",
    "sante": "healthcare, medical, green and white tones",
    "lsv": "educational, curious, purple and warm tones",
}


def make_image_prompt(titre, resume, categorie):
    """Use Claude to generate a specific DALL-E prompt for an article."""
    try:
        claude = anthropic.Anthropic()
        resp = claude.messages.create(
            model="claude-haiku-3-20240307",
            max_tokens=300,
            messages=[{"role": "user", "content": (
                f"Generate a DALL-E image prompt for this pharmacy news article.\n"
                f"Title: {titre}\nSummary: {resume}\nCategory: {categorie}\n\n"
                f"Rules:\n"
                f"- Describe a specific, concrete scene that illustrates this exact article\n"
                f"- Photorealistic editorial photography style\n"
                f"- Include specific visual details (objects, setting, lighting)\n"
                f"- NO text, NO logos, NO watermarks in the image\n"
                f"- 16:9 landscape format\n"
                f"- Reply ONLY with the prompt, nothing else"
            )}]
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"    [PROMPT-ERR] {e}")
        style_hint = CAT_STYLE.get(categorie, "pharmacy, healthcare")
        return (
            f"Editorial photo for article: {titre}. "
            f"Style: {style_hint}. Photorealistic, no text, no logos."
        )


def generate_article_image(article_id, titre, categorie, resume=""):
    """Generate a DALL-E image for an article. Returns relative path or empty string."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key:
        print("    [SKIP] OPENAI_API_KEY non definie")
        return ""

    ASSETS_DIR.mkdir(exist_ok=True)
    img_name = f"img_{article_id}.png"
    img_path = ASSETS_DIR / img_name

    if img_path.exists():
        return f"assets/{img_name}"

    prompt = make_image_prompt(titre, resume, categorie)

    try:
        client = OpenAI(api_key=openai_key)
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1792x1024",
            quality="standard",
            n=1,
        )
        url = response.data[0].url
        urllib.request.urlretrieve(url, str(img_path))
        print(f"    [IMG] {img_name} genere")
        return f"assets/{img_name}"
    except Exception as e:
        print(f"    [IMG-ERR] {e}")
        # Retry once after 65s if rate limited
        if "429" in str(e):
            print("    [IMG] Attente 65s (rate limit)...")
            time.sleep(65)
            try:
                client = OpenAI(api_key=openai_key)
                response = client.images.generate(
                    model="dall-e-3",
                    prompt=prompt,
                    size="1792x1024",
                    quality="standard",
                    n=1,
                )
                url = response.data[0].url
                urllib.request.urlretrieve(url, str(img_path))
                print(f"    [IMG] {img_name} genere (retry)")
                return f"assets/{img_name}"
            except Exception as e2:
                print(f"    [IMG-ERR] Retry echoue: {e2}")
        return ""


def update_index_html(new_articles):
    """Insert new articles into index.html's ARTICLES array."""
    html = INDEX_HTML.read_text(encoding="utf-8")

    # Trouver le tableau ARTICLES existant
    match = re.search(r"const ARTICLES = \[([\s\S]*?)\];", html)
    if not match:
        print("  [ERROR] ARTICLES array introuvable dans index.html")
        return False

    existing_block = match.group(1)

    # Parser les articles existants (extraire les IDs pour eviter les doublons)
    existing_ids = set(re.findall(r'id:\s*"([^"]+)"', existing_block))

    # Construire les nouveaux articles en JS
    today = datetime.now().strftime("%Y-%m-%d")
    new_js_entries = []

    for i, a in enumerate(new_articles):
        article_id = f"actu_{today.replace('-','_')}_{i+1}"
        if article_id in existing_ids:
            article_id += "_b"

        # Escape les quotes dans les textes
        def esc(s):
            return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

        default_source = "Pharm'Alpha"
        vals = {
            "id": article_id,
            "date": a.get("date", today),
            "categorie": a.get("categorie", "sante"),
            "titre": esc(a.get("titre", "")),
            "resume": esc(a.get("resume", "")),
            "full_text": esc(a.get("full_text", a.get("resume", ""))),
            "source": esc(a.get("source", default_source)),
            "source_url": a.get("source_url", ""),
            "badge_label": a.get("badge_label", "Sante"),
        }

        # Generer image DALL-E
        print(f"  [{i+1}/{len(new_articles)}] {vals['titre'][:50]}...")
        img_url = generate_article_image(
            article_id, a.get("titre", ""), vals["categorie"],
            resume=a.get("resume", "")
        )
        if i < len(new_articles) - 1 and img_url:
            time.sleep(62)  # Rate limit DALL-E: 1 img/min

        entry = (
            '  {\n'
            '    id: "' + vals["id"] + '",\n'
            '    date: "' + vals["date"] + '",\n'
            '    type: "actu",\n'
            '    categorie: "' + vals["categorie"] + '",\n'
            '    titre: "' + vals["titre"] + '",\n'
            '    resume: "' + vals["resume"] + '",\n'
            '    full_text: "' + vals["full_text"] + '",\n'
            '    source: "' + vals["source"] + '",\n'
            '    source_url: "' + vals["source_url"] + '",\n'
            '    tiktok_url: "",\n'
            '    badge_label: "' + vals["badge_label"] + '",\n'
            '    image_url: "' + img_url + '"\n'
            '  }'
        )
        new_js_entries.append(entry)

    if not new_js_entries:
        print("  Aucun nouvel article a ajouter")
        return False

    # Prepend les nouveaux articles (plus recents en premier)
    new_block = ",\n".join(new_js_entries)
    if existing_block.strip():
        updated_block = "\n" + new_block + ",\n" + existing_block.strip() + "\n"
    else:
        updated_block = "\n" + new_block + "\n"

    # Limiter le nombre total d'articles
    all_entries = re.findall(r"\{[^}]+\}", updated_block, re.DOTALL)
    if len(all_entries) > MAX_ARTICLES_TOTAL:
        # Garder seulement les MAX_ARTICLES_TOTAL premiers
        kept = all_entries[:MAX_ARTICLES_TOTAL]
        updated_block = "\n" + ",\n".join(kept) + "\n"

    updated_html = html[:match.start(1)] + updated_block + html[match.end(1):]
    INDEX_HTML.write_text(updated_html, encoding="utf-8")

    print(f"  {len(new_js_entries)} articles ajoutes a index.html")
    return True


def main():
    print("=== Pharm'Alpha - Mise a jour actus ===")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # 1. Fetch RSS
    print("\n[1/3] Collecte des flux RSS...")
    raw_articles = fetch_rss_articles()

    if not raw_articles:
        print("  Aucun article trouve. Arret.")
        return

    # 2. Curate avec Claude
    print(f"\n[2/3] Curation via Claude API ({len(raw_articles)} articles)...")
    curated = curate_with_claude(raw_articles)
    print(f"  {len(curated)} articles selectionnes")

    if not curated:
        print("  Aucun article curate. Arret.")
        return

    # 3. Update HTML
    print("\n[3/3] Mise a jour index.html...")
    updated = update_index_html(curated)

    if updated:
        print("\n=== Mise a jour terminee avec succes ===")
    else:
        print("\n=== Aucune mise a jour effectuee ===")


if __name__ == "__main__":
    main()
