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
from zoneinfo import ZoneInfo

PARIS_TZ = ZoneInfo("Europe/Paris")

import anthropic
import feedparser

BREVO_LIST_ID = 5  # "Newsletter Pharm'Alpha"
SENDER_EMAIL = "actus@pharmalpha.fr"
SENDER_NAME = "Pharm'Actus"
REPLY_TO_EMAIL = "stephen.pharmacien@gmail.com"


FALLBACK_MODEL = "claude-haiku-4-5-20251001"


def claude_create(client, **kwargs):
    """Call Claude API with retry + fallback to Haiku if Sonnet is overloaded."""
    original_model = kwargs.get("model", "")
    # 2 tentatives sur le modele principal
    for attempt in range(2):
        try:
            return client.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            if e.status_code in (429, 529) and attempt < 1:
                print(f"    [RETRY] Claude {e.status_code}, attente 30s...")
                time.sleep(30)
            elif e.status_code in (429, 529):
                # Fallback sur Haiku
                print(f"    [FALLBACK] {original_model} indisponible, bascule sur Haiku...")
                kwargs["model"] = FALLBACK_MODEL
                try:
                    return client.messages.create(**kwargs)
                except Exception:
                    raise e  # Renvoyer l'erreur originale
            else:
                raise


SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
INDEX_HTML = ROOT_DIR / "index.html"
FEEDS_JSON = SCRIPT_DIR / "rss_feeds.json"
ASSETS_DIR = ROOT_DIR / "assets"

MAX_ARTICLES_TOTAL = 50
MAX_AGE_DAYS = 7
NEW_ARTICLES_PER_RUN = 5  # 3 actus + 1 bonne nouvelle + 1 avenir pharma


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
                        "date": published.strftime("%Y-%m-%d") if published else datetime.now(PARIS_TZ).strftime("%Y-%m-%d"),
                    })
        except Exception as e:
            print(f"  [WARN] Erreur feed {feed_cfg['name']}: {e}")

    # Garder les 30 plus recents pour ne pas surcharger Claude
    articles.sort(key=lambda a: a["date"], reverse=True)
    articles = articles[:30]
    print(f"  {len(articles)} articles RSS retenus (30 max)")
    return articles


# ── CLAUDE : curation des actus (ton Stephen) ───────────────────────

def get_existing_source_urls():
    """Get source_urls already published on the site (to avoid duplicates)."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    return set(re.findall(r'source_url:\s*"([^"]+)"', html))


def curate_with_claude(raw_articles, existing_urls=None):
    """Select and rewrite the best articles with Stephen's personal tone."""
    client = anthropic.Anthropic()

    # Filtrer en amont les articles deja publies sur le site
    if existing_urls:
        before = len(raw_articles)
        raw_articles = [a for a in raw_articles if a.get("link", "") not in existing_urls]
        skipped = before - len(raw_articles)
        if skipped:
            print(f"  {skipped} articles RSS deja publies, exclus de la curation")

    articles_text = "\n\n".join(
        f"[{i+1}] {a['title']}\nSource: {a['source']} | Cat: {a['categorie']} | Date: {a['date']}\nResume: {a['summary']}\nLien: {a['link']}"
        for i, a in enumerate(raw_articles)
    )

    today = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")

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

Selectionne et redige EXACTEMENT 5 articles dans ces 5 categories :

**[1] PHARMA MONDE** (1 article OBLIGATOIRE) — Actu internationale pharma/sante
- Source etrangere UNIQUEMENT (Reuters, STAT News, Pharmaceutical Journal, Fierce Pharma, European Pharmaceutical Review, Pharmacy Times, Nature Medicine, BioPharma Dive, etc.)
- Traduis et adapte en francais avec le style Stephen. Explique l'impact pour un pharmacien francais.
- categorie : "pharma_monde"
- badge_label : "Pharma Monde"

**[2-3] ACTUS DU JOUR** (2 articles) — Les plus percutants pour les pharmaciens officinaux
- Impact direct sur l'exercice : reglementation, marges, missions, approvisionnement, reglementaire (LFSS, ROSP), sante publique
- categorie : "pharma_france" | "sante"
- badge_label : "Pharma France" | "Sante"

**[4] LA BONNE NOUVELLE** (1 article) — Une info positive, encourageante pour la profession
- Avancee pour les patients ou les pharmaciens, nouveau service valorise, remboursement obtenu, etude rassurante, innovation utile
- Si aucune vraie bonne nouvelle dans les articles, prends la moins mauvaise et formule-la positivement
- categorie : "bonne_nouvelle"
- badge_label : "La bonne nouvelle"

**[5] L'AVENIR DE LA PHARMA** (1 article) — R&D, innovation, pipeline, perspectives
- Medicament en developpement (phase 2/3/4), nouvelle molecule, technologie emergente (ARNm, CAR-T, IA, etc.), recherche prometteuse avec impact clinique futur
- Si peu d'articles R&D disponibles, extrais la dimension innovation/avenir d'un article existant
- categorie : "avenir_pharma"
- badge_label : "L'avenir de la pharma"

REGLES DE SOURCES :
1. Maximum 1 article par source (media). JAMAIS 2 articles du meme media.
2. ALTERNER les sources d'un jour a l'autre. Le Moniteur et Le Quotidien du Pharmacien sont des references, mais ne les utilise pas TOUS les jours. Alterne avec : Egora, HAS, Ordre des Pharmaciens, LEEM, Le Pharmacien de France, VIDAL, Sciences et Avenir, Pourquoi Docteur, APMnews, The Conversation, etc.
3. Pour Pharma Monde : UNIQUEMENT des sources etrangeres (Reuters, STAT News, Pharmaceutical Journal, Fierce Pharma, European Pharmaceutical Review, Pharmacy Times, Nature Medicine, BioPharma Dive). Traduis en francais.

Pour chaque article, genere :
- "titre" : accrocheur, max 80 car, style direct de Stephen
- "resume" : 2-3 phrases percutantes, angle pharmacien
- "full_text" : 150-250 mots, 4-5 paragraphes separes par \\n\\n. Style Stephen : phrases courtes, chiffres concrets, impact officine, humour si pertinent. 1ere phrase = accroche forte.
- "categorie" : voir ci-dessus
- "badge_label" : voir ci-dessus
- "source" et "source_url"
- "image_keywords" : 2-3 mots EN ANGLAIS pour chercher une photo libre de droit

JSON UNIQUEMENT (tableau de 5 objets) :
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
    today = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")

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

PEXELS_API_KEY = "UapwydwlfWpQrgkN8rfyClS3foJ6zuFYyL4UVqFYtomh7tlTVcM5t6g1"
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PharmActus/1.0)"}


def search_pexels_photo(query):
    """Search Pexels for a free stock photo. Returns (download_url, photographer)."""
    encoded = urllib.parse.quote(query)
    url = f"https://api.pexels.com/v1/search?query={encoded}&per_page=3&orientation=landscape"
    headers = {**HTTP_HEADERS, "Authorization": PEXELS_API_KEY}
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
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
        req = urllib.request.Request(url, headers=HTTP_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(str(dest_path), "wb") as f:
                f.write(resp.read())
        return True
    except Exception as e:
        print(f"    [DL-ERR] {e}")
        return False


STOCK_DIR = ASSETS_DIR / "stock"
_stock_usage = {}  # track which stock photos are used this run

NEWSLETTER_SENT_FILE = ROOT_DIR / "output" / "newsletter_sent.json"
PENDING_LSV_FILE = ROOT_DIR / "output" / "pending_lsv.json"


def get_fallback_photo(categorie):
    """Pick a stock fallback photo for the given category. Cycles through available photos."""
    cat = categorie if categorie in ("pharma_france", "pharma_monde", "sante", "lsv") else "sante"
    idx = _stock_usage.get(cat, 0)
    # 4 photos per category: cat_1.jpg .. cat_4.jpg
    photo_name = f"{cat}_{(idx % 4) + 1}.jpg"
    photo_path = STOCK_DIR / photo_name
    _stock_usage[cat] = idx + 1
    if photo_path.exists():
        dest_name = f"stock/{photo_name}"
        return dest_name
    return ""


def newsletter_already_sent_today():
    """Check if newsletter was already sent today."""
    today = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
    if NEWSLETTER_SENT_FILE.exists():
        try:
            data = json.loads(NEWSLETTER_SENT_FILE.read_text(encoding="utf-8"))
            if data.get("date") == today:
                return True
        except Exception:
            pass
    return False


def mark_newsletter_sent():
    """Mark newsletter as sent today."""
    today = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
    NEWSLETTER_SENT_FILE.parent.mkdir(exist_ok=True)
    NEWSLETTER_SENT_FILE.write_text(
        json.dumps({"date": today, "sent_at": datetime.now(PARIS_TZ).isoformat()}),
        encoding="utf-8"
    )


def load_pending_lsv():
    """Load a LSV saved from a previous run (not yet published)."""
    if PENDING_LSV_FILE.exists():
        try:
            lsv = json.loads(PENDING_LSV_FILE.read_text(encoding="utf-8"))
            lsv["date"] = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
            lsv.setdefault("categorie", "lsv")
            lsv.setdefault("badge_label", "Le Saviez-Vous")
            lsv.setdefault("source", "Pharm'Alpha")
            lsv.setdefault("source_url", "")
            print(f"  [LSV-PENDING] Utilisation du LSV en attente : {lsv.get('titre','')[:60]}...")
            return lsv
        except Exception as e:
            print(f"  [LSV-PENDING] Erreur: {e}")
    return None


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
    existing_urls = set(re.findall(r'source_url:\s*"([^"]+)"', existing_block))

    today = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
    ASSETS_DIR.mkdir(exist_ok=True)

    new_js_entries = []
    actu_idx = 0

    for a in new_articles:
        # Skip if same source URL already exists (avoid duplicates)
        src_url = a.get("source_url", "")
        if src_url and src_url in existing_urls:
            print(f"  [SKIP] Doublon source_url: {a.get('titre', '')[:50]}...")
            continue

        is_lsv = a.get("categorie") == "lsv"
        if is_lsv:
            article_id = f"lsv_{today.replace('-', '_')}"
        else:
            actu_idx += 1
            article_id = f"actu_{today.replace('-', '_')}_{actu_idx}"
        while article_id in existing_ids:
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

        # Photo : Pexels API → fallback stock local
        img_url = ""
        pexels_cdn_url = ""  # URL CDN directe pour l'email (dispo avant deploiement)
        img_keywords = a.get("image_keywords", "")
        print(f"  [{new_articles.index(a)+1}/{len(new_articles)}] {vals['titre'][:55]}...")
        if img_keywords:
            photo_url, photographer = search_pexels_photo(img_keywords)
            if photo_url:
                pexels_cdn_url = photo_url  # Sauvegarde URL CDN pour l'email
                img_name = f"img_{article_id}.jpg"
                img_path = ASSETS_DIR / img_name
                if download_photo(photo_url, img_path):
                    img_url = f"assets/{img_name}"
                    print(f"    [IMG] {img_name} (Pexels{' - ' + photographer if photographer else ''})")
        if not img_url:
            # Fallback : photo stock pre-telechargee par categorie
            fallback = get_fallback_photo(a.get("categorie", "sante"))
            if fallback:
                img_url = f"assets/{fallback}"
                print(f"    [IMG-FALLBACK] {fallback}")

        # Mettre a jour le dict article pour que la newsletter ait aussi l'image
        a["image_url"] = img_url
        # Email: URL Pexels CDN directe (disponible avant deploiement Pages)
        # Pour les photos stock : elles sont committees, l'URL hébergée est stable
        if pexels_cdn_url:
            a["email_image_url"] = pexels_cdn_url
        elif img_url:
            a["email_image_url"] = f"https://actus.pharmalpha.fr/{img_url}"
        else:
            a["email_image_url"] = ""
        a["id"] = article_id

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

    # Generate individual article pages for social sharing
    generate_article_pages(new_articles)

    return True


def generate_article_pages(articles):
    """Generate individual HTML pages for each article (og:tags for social sharing)."""
    articles_dir = ROOT_DIR / "articles"
    articles_dir.mkdir(exist_ok=True)

    for a in articles:
        article_id = a.get("id", "")
        if not article_id:
            continue

        titre = a.get("titre", "").replace('"', "&quot;")
        resume = a.get("resume", "").replace('"', "&quot;")
        image_url = a.get("image_url", "")
        if image_url:
            og_image = f"https://actus.pharmalpha.fr/{image_url}"
        else:
            og_image = "https://actus.pharmalpha.fr/assets/og_image.png"

        page_html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titre} - Pharm'Actus</title>
<meta property="og:title" content="{titre}" />
<meta property="og:description" content="{resume}" />
<meta property="og:image" content="{og_image}" />
<meta property="og:url" content="https://actus.pharmalpha.fr/articles/{article_id}.html" />
<meta property="og:type" content="article" />
<meta property="og:site_name" content="Pharm'Actus" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{titre}" />
<meta name="twitter:description" content="{resume}" />
<meta name="twitter:image" content="{og_image}" />
<meta http-equiv="refresh" content="0;url=https://actus.pharmalpha.fr/?a={article_id}" />
</head>
<body>
<p>Redirection vers <a href="https://actus.pharmalpha.fr/?a={article_id}">Pharm'Actus</a>...</p>
</body>
</html>'''

        page_path = articles_dir / f"{article_id}.html"
        page_path.write_text(page_html, encoding="utf-8")

    print(f"  {len(articles)} pages article generees dans articles/")


# ── BREVO : envoi newsletter ──────────────────────────────────────────

def generate_email_intro(articles):
    """Generate a unique daily email intro using Claude, referencing an article."""
    actus = [a for a in articles if a.get("categorie") != "lsv"]
    lsv = next((a for a in articles if a.get("categorie") == "lsv"), None)
    titres = [a.get("titre", "") for a in actus]
    lsv_titre = lsv.get("titre", "") if lsv else ""

    prompt = f"""Tu es Stephen, pharmacien devenu consultant pharma. Tu ecris l'intro de ta newsletter quotidienne Pharm'Actus.

Voici les actus du jour :
{chr(10).join(f'- {t}' for t in titres)}
{f'- Le Saviez-Vous : {lsv_titre}' if lsv_titre else ''}

Ecris une intro de 2-3 phrases MAX (pas plus de 50 mots). Regles :
- Tutoie le lecteur
- Ton decontracte, direct, un peu piquant
- Fais reference a UNE ou DEUX actus du jour de maniere accrocheuse (teaser, sans donner la reponse)
- Finis par "Bonne lecture !" ou une variante
- PAS de emoji, PAS de guillemets autour du texte
- Ecris en HTML avec les entites pour les accents (&eacute; &agrave; &egrave; &ecirc; &ucirc; &icirc; &ocirc; &ccedil; etc.)

ATTENTION ORTHOGRAPHE : relis-toi avant de repondre. ZERO faute tolere.
- Verifie chaque mot accentue (co&ucirc;ter, d&eacute;j&agrave;, r&eacute;cent, etc.)
- Verifie les accords (pluriel, participe passe)
- Si tu as un doute sur un mot, reformule avec un mot plus simple
- Exemples de fautes a ne PAS faire : "coitait" au lieu de "co&ucirc;tait", "lache" au lieu de "l&acirc;che", etc."""

    try:
        client = anthropic.Anthropic()
        response = claude_create(client,
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        intro = response.content[0].text.strip()
        # Nettoyage : enlever guillemets si Claude en ajoute
        intro = intro.strip('"').strip("'").strip("\u00ab\u00bb")
        print(f"  [EMAIL-INTRO] Intro generee: {intro[:60]}...")
        return intro
    except Exception as e:
        print(f"  [EMAIL-INTRO] Erreur Claude, fallback statique: {e}")
        return None


def build_newsletter_html(articles, custom_intro=None):
    """Build newsletter HTML from today's articles."""
    today = datetime.now(PARIS_TZ)
    jours = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    mois_noms = ["","janvier","f\u00e9vrier","mars","avril","mai","juin",
                 "juillet","ao\u00fbt","septembre","octobre","novembre","d\u00e9cembre"]
    date_str = f"{jours[today.weekday()]} {today.day} {mois_noms[today.month]} {today.year}"

    actus = [a for a in articles if a.get("categorie") != "lsv"]
    lsv = next((a for a in articles if a.get("categorie") == "lsv"), None)
    n_total = len(actus)
    count_str = f"{n_total} actu{'s' if n_total > 1 else ''}" + (" + 1 histoire" if lsv else "")

    badge_colors = {
        "pharma_france": ("#fff7ed", "#f97316"),
        "pharma_monde": ("#eff6ff", "#2563eb"),
        "sante": ("#f0fdf4", "#16a34a"),
        "bonne_nouvelle": ("#f0fdfa", "#0d9488"),
        "avenir_pharma": ("#eef2ff", "#4f46e5"),
    }

    def article_url(article):
        aid = article.get("id", "")
        return f"https://actus.pharmalpha.fr/articles/{aid}.html" if aid else "https://actus.pharmalpha.fr/"

    articles_html = ""
    for i, a in enumerate(actus):
        bg, fg = badge_colors.get(a.get("categorie", ""), ("#fff7ed", "#f97316"))
        pad = "24px" if i == 0 else "20px"
        email_img = a.get("email_image_url") or a.get("image_url", "")
        img_html = ""
        art_url = article_url(a)
        if email_img:
            full_url = email_img if email_img.startswith("http") else f"https://actus.pharmalpha.fr/{email_img}"
            img_html = f'<tr><td style="padding-top:12px;"><a href="{art_url}"><img src="{full_url}" alt="" width="536" style="width:100%;max-width:536px;height:auto;border-radius:8px;display:block;border:0;" /></a></td></tr>'
        articles_html += f'''
  <tr><td style="padding:{pad} 32px 0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td><span style="display:inline-block;background:{bg};color:{fg};font-size:11px;font-weight:700;padding:3px 10px;border-radius:100px;text-transform:uppercase;letter-spacing:0.4px;">{a.get("badge_label","")}</span></td></tr>
      {img_html}
      <tr><td style="padding-top:10px;"><a href="{art_url}" style="font-size:18px;font-weight:700;color:#1a1a1a;text-decoration:none;line-height:1.35;">{a.get("titre","")}</a></td></tr>
      <tr><td style="padding-top:8px;"><p style="margin:0;font-size:14px;color:#555;line-height:1.6;">{a.get("resume","")}</p></td></tr>
      <tr><td style="padding-top:10px;"><span style="font-size:12px;color:#888;">Source : {a.get("source","")}</span></td></tr>
    </table>
  </td></tr>
  <tr><td style="padding:20px 32px 0;"><div style="border-top:1px solid #f0f0f0;"></div></td></tr>'''

    if lsv:
        lsv_url = article_url(lsv)
        articles_html += f'''
  <tr><td style="padding:24px 32px 0;"><div style="border-top:2px solid #7c3aed;"></div></td></tr>
  <tr><td style="padding:20px 32px 0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f3ff;border-radius:10px;overflow:hidden;">
      <tr><td style="padding:20px 24px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          <tr><td><span style="display:inline-block;background:#ede9fe;color:#7c3aed;font-size:11px;font-weight:700;padding:3px 10px;border-radius:100px;text-transform:uppercase;letter-spacing:0.4px;">Le Saviez-Vous</span></td></tr>
          <tr><td style="padding-top:12px;"><a href="{lsv_url}" style="font-size:18px;font-weight:700;color:#1a1a1a;text-decoration:none;line-height:1.35;">{lsv.get("titre","")}</a></td></tr>
          <tr><td style="padding-top:8px;"><p style="margin:0;font-size:14px;color:#555;line-height:1.6;">{lsv.get("resume","")}</p></td></tr>
        </table>
      </td></tr>
    </table>
  </td></tr>'''

    return f'''<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{count_str} &mdash; {date_str}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
  <tr><td style="background:#ffffff;padding:28px 32px 16px;text-align:center;border-bottom:2px solid #f97316;">
    <a href="https://actus.pharmalpha.fr/" style="text-decoration:none;"><span style="font-size:32px;font-weight:800;color:#1a1a1a;letter-spacing:-0.5px;">Pharm'<span style="color:#f97316;">Actus</span></span></a><br>
    <span style="font-size:13px;color:#888;letter-spacing:0.3px;">Chaque matin, retrouve l'actus pharma &agrave; lire entre deux ordo.</span>
  </td></tr>
  <tr><td style="background:#fafafa;padding:10px 32px;text-align:center;">
    <span style="color:#1a1a1a;font-size:14px;font-weight:600;">{date_str}</span>
    <span style="color:#888;font-size:14px;"> &mdash; {count_str}</span>
  </td></tr>
  <tr><td style="padding:28px 32px 20px;">
    <p style="margin:0;font-size:15px;color:#333;line-height:1.6;">
      {custom_intro if custom_intro else "Hey, je sais que tu es press&eacute;, tu as tellement de choses &agrave; faire ! C'est pourquoi je t'ai s&eacute;lectionn&eacute; les 5 actus du jour &agrave; ne pas manquer &mdash; dont une bonne nouvelle et un regard sur l'avenir de la pharma. Et m&ecirc;me une histoire pharma pour ta pause caf&eacute;. Bonne lecture !"}
    </p>
    <p style="margin:12px 0 0;font-size:13px;color:#999;line-height:1.5;font-style:italic;">
      Astuce : r&eacute;ponds juste &laquo; bien re&ccedil;u &raquo; &agrave; cet email. &Ccedil;a indique &agrave; ta messagerie qu'on se conna&icirc;t, et mes actus atterriront toujours dans ta bo&icirc;te principale.
    </p>
  </td></tr>
  <tr><td style="padding:0 32px;"><div style="border-top:1px solid #e5e5e5;"></div></td></tr>
  {articles_html}
  <tr><td style="padding:28px 32px 0;" align="center">
    <table role="presentation" cellpadding="0" cellspacing="0"><tr>
      <td style="background:#f97316;border-radius:8px;">
        <a href="https://actus.pharmalpha.fr/" style="display:inline-block;padding:14px 32px;color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;letter-spacing:0.3px;">Lire les articles complets &rarr;</a>
      </td>
    </tr></table>
  </td></tr>
  <tr><td style="padding:28px 32px 0;">
    <div style="border-top:1px solid #e5e5e5;padding-top:20px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="vertical-align:top;width:70px;padding-right:16px;">
            <img src="https://actus.pharmalpha.fr/assets/stephen.png" alt="Stephen ROBERT" width="60" height="60" style="width:60px;height:60px;border-radius:50%;display:block;" />
          </td>
          <td style="vertical-align:top;">
            <p style="margin:0 0 2px;font-size:15px;font-weight:700;color:#1a1a1a;">Stephen ROBERT</p>
            <p style="margin:0 0 8px;font-size:12px;font-weight:600;color:#f97316;">Consultant, Formateur &amp; Communicant Pharma</p>
            <p style="margin:0;font-size:13px;color:#666;line-height:1.5;">Docteur en Pharmacie, dipl&ocirc;m&eacute; d'un Mast&egrave;re Marketing &amp; Management des Industries de Sant&eacute;. Avec Pharm'Actus, je d&eacute;crypte l'actu pharma chaque matin pour que tu restes <em>in</em>, sans y passer des heures.</p>
          </td>
        </tr>
      </table>
    </div>
  </td></tr>
  <tr><td style="padding:20px 32px 28px;">
    <div style="border-top:1px solid #f0f0f0;padding-top:16px;text-align:center;">
      <p style="margin:0 0 8px;font-size:13px;font-weight:700;color:#f97316;">Pharm'Alpha</p>
      <p style="margin:0;font-size:11px;color:#aaa;line-height:1.5;">
        Tu re&ccedil;ois cet email car tu t'es inscrit(e) sur
        <a href="https://actus.pharmalpha.fr/" style="color:#888;">Pharm'Actus</a>.<br>
        <a href="{{{{ unsubscribe }}}}" style="color:#888;">Se d&eacute;sinscrire</a> &bull;
        <a href="https://actus.pharmalpha.fr/" style="color:#888;">Voir en ligne</a>
      </p>
    </div>
  </td></tr>
</table>
</td></tr></table>
</body></html>'''


def send_newsletter(articles):
    """Send newsletter individually to each contact in the Brevo list."""
    if newsletter_already_sent_today():
        print("  [SKIP] Newsletter deja envoyee aujourd'hui - une seule newsletter par jour")
        return

    api_key = os.environ.get("BREVO_API_KEY", "")
    if not api_key:
        print("  [SKIP] BREVO_API_KEY non definie, email non envoye")
        return

    # Fetch ALL contacts with pagination (50 per page)
    all_contacts = []
    offset = 0
    limit = 50
    headers = {"api-key": api_key, "Accept": "application/json"}
    while True:
        url = f"https://api.brevo.com/v3/contacts/lists/{BREVO_LIST_ID}/contacts?limit={limit}&offset={offset}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
            contacts = data.get("contacts", [])
            all_contacts.extend(contacts)
            if len(contacts) < limit:
                break
            offset += limit
        except Exception as e:
            print(f"  [BREVO-ERR] Impossible de recuperer les contacts: {e}")
            return

    if not all_contacts:
        print("  [INFO] Aucun abonne dans la liste, email non envoye")
        return

    emails = [c["email"] for c in all_contacts if c.get("email")]
    print(f"  {len(emails)} abonne(s) dans la liste")

    # Generate personalized intro via Claude
    custom_intro = generate_email_intro(articles)

    # Build email
    html_content = build_newsletter_html(articles, custom_intro=custom_intro)
    today = datetime.now(PARIS_TZ)
    jours = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    mois_noms = ["","janvier","f\u00e9vrier","mars","avril","mai","juin",
                 "juillet","ao\u00fbt","septembre","octobre","novembre","d\u00e9cembre"]
    date_str = f"{jours[today.weekday()]} {today.day} {mois_noms[today.month]} {today.year}"
    subject = f"Pharm'Actus du {date_str}"

    # Send individually to each contact (privacy: no one sees others' emails)
    send_url = "https://api.brevo.com/v3/smtp/email"
    sent = 0
    errors = 0
    for email in emails:
        payload = json.dumps({
            "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
            "replyTo": {"email": REPLY_TO_EMAIL, "name": SENDER_NAME},
            "to": [{"email": email}],
            "subject": subject,
            "htmlContent": html_content,
        }).encode("utf-8")
        try:
            req = urllib.request.Request(
                send_url,
                data=payload,
                headers={
                    "api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req) as resp:
                json.loads(resp.read())
            sent += 1
        except Exception as e:
            errors += 1
            print(f"  [BREVO-ERR] Echec pour {email}: {e}")

    print(f"  Newsletter envoyee a {sent}/{len(emails)} abonne(s)" +
          (f" ({errors} erreur(s))" if errors else ""))
    if sent > 0:
        mark_newsletter_sent()
        print("  [SENT-MARK] Newsletter marquee comme envoyee aujourd'hui")


# ── MAIN ──────────────────────────────────────────────────────────────

def main():
    print("=== Pharm'Actus - Mise a jour quotidienne ===")
    print(f"  Date: {datetime.now(PARIS_TZ).strftime('%Y-%m-%d %H:%M')}")

    # 1. Fetch RSS
    print("\n[1/5] Collecte des flux RSS...")
    raw_articles = fetch_rss_articles()
    if not raw_articles:
        print("  Aucun article RSS. Arret.")
        return

    # 2. Curate 5 articles (3 actus + 1 bonne nouvelle + 1 avenir pharma)
    existing_urls = get_existing_source_urls()
    print(f"\n[2/5] Curation via Claude ({len(raw_articles)} articles, {len(existing_urls)} deja publies)...")
    curated = curate_with_claude(raw_articles, existing_urls)
    print(f"  {len(curated)} actus selectionnees")

    # 3. Generate 1 Le Saviez-Vous (ou utiliser le LSV en attente)
    print("\n[3/5] Generation du Le Saviez-Vous...")
    existing_lsv = get_existing_lsv_titles()
    lsv = load_pending_lsv() or generate_lsv_with_claude(existing_lsv)
    if lsv:
        print(f"  LSV: {lsv.get('titre', '')[:60]}...")
        curated.append(lsv)
        # Export LSV for TikTok video pipeline
        lsv_output_dir = ROOT_DIR / "output"
        lsv_output_dir.mkdir(exist_ok=True)
        lsv_output_file = lsv_output_dir / "latest_lsv.json"
        with open(lsv_output_file, "w", encoding="utf-8") as lsv_f:
            json.dump(lsv, lsv_f, ensure_ascii=False, indent=2)
        print(f"  [LSV-EXPORT] Sauvegarde dans output/latest_lsv.json")
        # Supprimer le fichier pending s'il a ete utilise
        if PENDING_LSV_FILE.exists():
            PENDING_LSV_FILE.unlink()
            print("  [LSV-PENDING] Fichier pending supprime apres utilisation")
    else:
        print("  [WARN] Pas de LSV genere")

    if not curated:
        print("  Rien a publier. Arret.")
        return

    # 4. Photos + insertion HTML
    print("\n[4/5] Photos + mise a jour index.html...")
    updated = update_index_html(curated)

    if updated:
        # 5. Send newsletter (uniquement les articles effectivement ajoutes)
        added = [a for a in curated if a.get("id")]
        print(f"\n[5/5] Envoi newsletter Brevo ({len(added)} articles)...")
        send_newsletter(added)
        print("\n=== Mise a jour terminee avec succes ===")
    else:
        print("\n=== Aucune mise a jour effectuee ===")


if __name__ == "__main__":
    main()
