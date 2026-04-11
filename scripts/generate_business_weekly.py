#!/usr/bin/env python3
"""
Pharm'Actus - Business Officine Hebdo
Genere chaque lundi un article analytique business officine et le publie directement
- Scanne les RSS des 7 derniers jours
- Claude selectionne le sujet business le plus impactant
- Redige un article 600-800 mots avec chiffres + sources citees
- Sauvegarde l'archive dans DRAFTS/business/YYYY-MM-DD.md
- Publie directement dans index.html (categorie business_officine)
- Envoie email d'information a Stephen

Usage:
  ANTHROPIC_API_KEY=sk-... BREVO_API_KEY=xkeysib-... python scripts/generate_business_weekly.py
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

import anthropic
import feedparser

PARIS_TZ = ZoneInfo("Europe/Paris")

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
FEEDS_JSON = SCRIPT_DIR / "rss_feeds.json"
DRAFTS_DIR = ROOT_DIR / "DRAFTS" / "business"

MAX_AGE_DAYS = 7
MAX_ARTICLES_FOR_CLAUDE = 40

# Sources prioritaires pour l'angle business officine
BUSINESS_PRIORITY_SOURCES = {
    "Le Moniteur des Pharmacies",
    "Le Quotidien du Pharmacien",
    "Le Pharmacien de France",
    "LEEM",
    "HAS Actualites",
    "ANSM Actualites",
    "Ordre des Pharmaciens",
    "APMnews Pharma",
    "Egora",
}

BREVO_API_BASE = "https://api.brevo.com/v3"
SENDER_EMAIL = "actus@pharmalpha.fr"
SENDER_NAME = "Pharm'Actus Drafts"
EMAIL_RECIPIENT = "stephen.pharmacien@gmail.com"

FALLBACK_MODEL = "claude-haiku-4-5-20251001"


def claude_create(client, **kwargs):
    """Call Claude API with retry + fallback to Haiku if Sonnet overloaded."""
    original_model = kwargs.get("model", "")
    for attempt in range(2):
        try:
            return client.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            if e.status_code in (429, 529) and attempt < 1:
                print(f"  [RETRY] Claude {e.status_code}, attente 30s...")
                time.sleep(30)
            elif e.status_code in (429, 529):
                print(f"  [FALLBACK] {original_model} indisponible, bascule sur Haiku...")
                kwargs["model"] = FALLBACK_MODEL
                try:
                    return client.messages.create(**kwargs)
                except Exception:
                    raise e
            else:
                raise


def fetch_rss_articles():
    """Fetch articles from all RSS feeds, last 7 days, prioritize business sources."""
    with open(FEEDS_JSON) as f:
        config = json.load(f)

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    articles = []

    for feed_cfg in config["feeds"]:
        try:
            feed = feedparser.parse(feed_cfg["url"])
            for entry in feed.entries[:20]:
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
                summary = re.sub(r"<[^>]+>", "", getattr(entry, "summary", "").strip())[:800]
                link = getattr(entry, "link", "")

                if title:
                    articles.append({
                        "title": title,
                        "summary": summary,
                        "link": link,
                        "source": feed_cfg["name"],
                        "categorie": feed_cfg["categorie"],
                        "date": published.strftime("%Y-%m-%d") if published else datetime.now().strftime("%Y-%m-%d"),
                        "is_priority": feed_cfg["name"] in BUSINESS_PRIORITY_SOURCES,
                    })
        except Exception as e:
            print(f"  [WARN] Erreur feed {feed_cfg['name']}: {e}")

    # Priorite aux sources business, puis par date
    articles.sort(key=lambda a: (not a["is_priority"], a["date"]), reverse=False)
    articles.sort(key=lambda a: a["date"], reverse=True)
    articles = articles[:MAX_ARTICLES_FOR_CLAUDE]
    print(f"  {len(articles)} articles RSS retenus pour la curation business")
    return articles


def generate_business_article(raw_articles):
    """Use Claude to pick the week's top business topic + write the article."""
    client = anthropic.Anthropic()

    today = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
    week_start = (datetime.now(PARIS_TZ) - timedelta(days=7)).strftime("%Y-%m-%d")

    articles_text = "\n\n".join(
        f"[{i+1}] {a['title']}\nSource: {a['source']} | Date: {a['date']}\nResume: {a['summary']}\nLien: {a['link']}"
        for i, a in enumerate(raw_articles)
    )

    prompt = f"""Tu es Stephen ROBERT, pharmacien consultant chez Pharm'Alpha et redacteur en chef de Pharm'Actus.

Tu rediges un article analytique hebdomadaire "BUSINESS OFFICINE" qui sera publie chaque lundi matin.

=== OBJECTIF DE LA RUBRIQUE ===
Donner aux pharmaciens titulaires une lecture BUSINESS claire de l'actu de la semaine :
- Impact economique sur l'officine (chiffres concrets, marges, ROSP, honoraires, missions)
- Enjeux reglementaires qui vont changer la donne
- Opportunites business a saisir
- Decryptage de rapports officiels (LEEM, HAS, ANSM, Cour des comptes, LFSS, IGAS)

=== TON STYLE ===
- Direct, decontracte, tutoiement
- MAIS plus analytique que les actus quotidiennes : tu es consultant business, pas journaliste
- Chiffres OBLIGATOIRES a chaque argument (euros, %, nombre de pharmacies, etc.)
- Reference a un rapport, une etude, une source officielle quand possible
- Langue professionnelle mais accessible
- Phrases courtes qui vont droit au but
- Conclus avec un insight actionable : "voici ce que tu peux faire des demain"

=== CRITERES DE SELECTION DU SUJET ===
1. Sujet avec un VRAI impact business (pas juste une actu info)
2. Avec des chiffres publics verifiables
3. Qui touche la RENTABILITE, les MARGES, les MISSIONS, la REGLEMENTATION, ou le MARCHE
4. Evite les sujets deja traites dans les actus quotidiennes (choisir un angle plus analytique)

=== ARTICLES DE LA SEMAINE ({week_start} → {today}) ===
{articles_text}

---

INSTRUCTION : Parmi ces {len(raw_articles)} articles, identifie LE SUJET BUSINESS le plus percutant de la semaine pour les pharmaciens titulaires.

Ecris un article analytique structure comme suit :

1. **Titre** (max 90 car) : accrocheur, oriente business avec un chiffre si possible
2. **Chapo / Accroche** (2-3 phrases, 40 mots max) : le chiffre choc ou l'enjeu central
3. **Contexte** (150-200 mots) : de quoi parle-t-on, depuis quand, qui est concerne
4. **Analyse business** (250-350 mots) : decryptage, chiffres precis, comparaisons, impact concret sur les marges / le CA / les missions. AU MOINS 3 chiffres verifiables.
5. **Recommandations actionnables** (100-150 mots) : 3-5 actions concretes que Stephen recommanderait a un titulaire en consultation
6. **Sources citees** (liste) : toutes les sources utilisees avec leurs URLs

REGLE ABSOLUE : chaque chiffre cite doit avoir une source. Si tu n'es pas SUR d'un chiffre, ecris "[A VERIFIER]" a cote. Stephen relira le brouillon avant publication.

Retourne le tout au format JSON :
{{
  "titre": "...",
  "chapo": "...",
  "contexte": "...",
  "analyse": "...",
  "recommandations": "...",
  "sources": [
    {{"nom": "...", "url": "..."}},
    ...
  ],
  "confidence_score": 0.X,
  "warnings": ["liste des incertitudes / chiffres a verifier"]
}}

Le `confidence_score` (0-1) reflete ton niveau de certitude sur la qualite des chiffres :
- 0.9+ = tous les chiffres sont verifies et datent de moins de 6 mois
- 0.7-0.9 = chiffres fiables mais peuvent etre legerement obsoletes
- <0.7 = plusieurs chiffres a verifier manuellement"""

    response = claude_create(
        client,
        model="claude-sonnet-4-20250514",
        max_tokens=5000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError as e:
            print(f"  [ERROR] JSON parse: {e}")
            return None
    print("  [ERROR] Pas de JSON valide dans la reponse Claude")
    return None


def save_archive(article):
    """Save the full article as markdown in DRAFTS/business/ (for history/archive)."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
    archive_path = DRAFTS_DIR / f"{today}.md"

    sources_md = "\n".join(
        f"- [{s['nom']}]({s['url']})" for s in article.get("sources", [])
    )
    warnings = article.get("warnings", [])
    warnings_md = "\n".join(f"- ⚠️ {w}" for w in warnings) if warnings else "_Aucune alerte_"
    confidence = article.get("confidence_score", 0)

    md = f"""---
type: business_officine
date: {today}
status: PUBLISHED
confidence_score: {confidence}
generated_at: {datetime.now(PARIS_TZ).isoformat()}
---

# {article["titre"]}

**Score de confiance : {confidence*100:.0f}%**

## Chapo

{article["chapo"]}

## Contexte

{article["contexte"]}

## Analyse business

{article["analyse"]}

## Recommandations actionnables

{article["recommandations"]}

## Sources

{sources_md}

## ⚠️ Points signales par Claude (a verifier)

{warnings_md}
"""

    archive_path.write_text(md, encoding="utf-8")
    print(f"  [ARCHIVE] Sauvegarde : {archive_path}")
    return archive_path


# ── PUBLICATION DIRECTE DANS INDEX.HTML ──────────────────────────────

INDEX_HTML = ROOT_DIR / "index.html"
ARTICLES_DIR = ROOT_DIR / "articles"


def esc_js(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def build_full_text(article):
    """Combine all sections into a single full_text for display on the site."""
    parts = []
    if article.get("chapo"):
        parts.append(article["chapo"])
    if article.get("contexte"):
        parts.append("**Contexte**\n\n" + article["contexte"])
    if article.get("analyse"):
        parts.append("**Analyse business**\n\n" + article["analyse"])
    if article.get("recommandations"):
        parts.append("**Recommandations actionnables**\n\n" + article["recommandations"])
    if article.get("sources"):
        src_list = "\n".join(f"- {s['nom']}" for s in article["sources"])
        parts.append("**Sources**\n\n" + src_list)
    return "\n\n".join(parts)


def publish_article_to_site(article):
    """Inject the business article into index.html + generate article page."""
    if not INDEX_HTML.exists():
        print("  [ERROR] index.html introuvable, publication impossible")
        return None

    html = INDEX_HTML.read_text(encoding="utf-8")
    match = re.search(r"const ARTICLES = \[([\s\S]*?)\];", html)
    if not match:
        print("  [ERROR] ARTICLES array introuvable dans index.html")
        return None

    date = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
    article_id = f"business_{date.replace('-', '_')}"

    existing_block = match.group(1)
    if f'id: "{article_id}"' in existing_block:
        print(f"  [SKIP] Article {article_id} deja publie cette semaine")
        return article_id

    full_text = build_full_text(article)
    chapo = article.get("chapo", "")
    resume = chapo[:220] + ("..." if len(chapo) > 220 else "")

    # Tags
    tags = ["business", "analyse", "hebdo", "chiffres"]
    tags_js = "[" + ", ".join(f'"{t}"' for t in tags) + "]"

    # Source principale = premiere source
    sources = article.get("sources", [])
    source = sources[0]["nom"] if sources else "Pharm'Alpha"
    source_url = sources[0]["url"] if sources else ""

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
    print(f"  [HTML] Article injecte dans index.html (id: {article_id})")

    # Generate individual article page (og:tags for social sharing)
    ARTICLES_DIR.mkdir(exist_ok=True)
    titre_safe = article["titre"].replace('"', "&quot;")
    resume_safe = resume.replace('"', "&quot;").replace("\n", " ")
    page_html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titre_safe} &mdash; Pharm'Actus Business</title>
<meta property="og:title" content="{titre_safe}" />
<meta property="og:description" content="{resume_safe}" />
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
    (ARTICLES_DIR / f"{article_id}.html").write_text(page_html, encoding="utf-8")
    print(f"  [PAGE] articles/{article_id}.html")

    return article_id


def send_published_email(article, article_id):
    """Send info email to Stephen: article auto-published this morning."""
    api_key = os.environ.get("BREVO_API_KEY", "")
    if not api_key:
        print("  [SKIP] BREVO_API_KEY non definie, email non envoye")
        return

    today = datetime.now(PARIS_TZ).strftime("%d/%m/%Y")
    confidence = article.get("confidence_score", 0)
    confidence_color = "#16a34a" if confidence >= 0.85 else ("#f97316" if confidence >= 0.7 else "#dc2626")
    warnings = article.get("warnings", [])
    sources = article.get("sources", [])
    article_url = f"https://actus.pharmalpha.fr/articles/{article_id}.html"

    sources_html = "".join(
        f'<li style="margin-bottom:6px;"><a href="{s["url"]}" style="color:#f97316;">{s["nom"]}</a></li>'
        for s in sources
    )
    warnings_html = "".join(
        f'<li style="margin-bottom:4px;">⚠️ {w}</li>' for w in warnings
    ) if warnings else '<li style="color:#16a34a;">✓ Aucune alerte signal&eacute;e</li>'

    def nl2br(text):
        return text.replace("\n\n", "</p><p>").replace("\n", "<br>")

    html = f'''<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;color:#1a1a1a;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="680" cellpadding="0" cellspacing="0" style="max-width:680px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06);">

  <tr><td style="background:#065f46;padding:20px 28px;border-bottom:3px solid #065f46;">
    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#a7f3d0;margin-bottom:6px;">✓ PUBLI&Eacute; CE MATIN</div>
    <div style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">Business Officine &mdash; {today}</div>
    <div style="font-size:13px;color:#a7f3d0;margin-top:6px;">Article auto-publi&eacute; sur le site. Relis pour verifier les chiffres et me dire si tu veux ajuster.</div>
  </td></tr>

  <tr><td style="padding:20px 28px;background:#f0fdf4;border-bottom:1px solid #d1fae5;">
    <table role="presentation" width="100%"><tr>
      <td>
        <div style="font-size:11px;text-transform:uppercase;font-weight:700;color:#666;letter-spacing:0.5px;margin-bottom:4px;">Score de confiance</div>
        <div style="font-size:28px;font-weight:800;color:{confidence_color};line-height:1;">{confidence*100:.0f}%</div>
      </td>
      <td align="right">
        <a href="{article_url}" style="display:inline-block;background:#f97316;color:#fff;padding:10px 20px;border-radius:100px;text-decoration:none;font-size:13px;font-weight:700;">Voir sur le site &rarr;</a>
      </td>
    </tr></table>
  </td></tr>

  <tr><td style="padding:28px 28px 8px;">
    <h1 style="margin:0 0 12px;font-size:24px;font-weight:800;color:#1a1a1a;line-height:1.3;letter-spacing:-0.3px;">{article["titre"]}</h1>
    <div style="font-size:15px;color:#f97316;font-weight:600;font-style:italic;margin-bottom:16px;border-left:3px solid #f97316;padding-left:14px;">{article["chapo"]}</div>
  </td></tr>

  <tr><td style="padding:0 28px 8px;">
    <h2 style="font-size:13px;text-transform:uppercase;letter-spacing:0.5px;color:#666;margin:16px 0 8px;font-weight:700;">Contexte</h2>
    <p style="margin:0;font-size:15px;color:#333;line-height:1.7;">{nl2br(article["contexte"])}</p>
  </td></tr>

  <tr><td style="padding:0 28px 8px;">
    <h2 style="font-size:13px;text-transform:uppercase;letter-spacing:0.5px;color:#666;margin:20px 0 8px;font-weight:700;">Analyse Business</h2>
    <p style="margin:0;font-size:15px;color:#333;line-height:1.7;">{nl2br(article["analyse"])}</p>
  </td></tr>

  <tr><td style="padding:0 28px 8px;">
    <div style="background:#fff7ed;border-left:4px solid #f97316;padding:16px 20px;border-radius:6px;margin-top:20px;">
      <h2 style="font-size:13px;text-transform:uppercase;letter-spacing:0.5px;color:#f97316;margin:0 0 8px;font-weight:700;">✦ Recommandations actionnables</h2>
      <p style="margin:0;font-size:14px;color:#1a1a1a;line-height:1.7;">{nl2br(article["recommandations"])}</p>
    </div>
  </td></tr>

  <tr><td style="padding:20px 28px 8px;">
    <h2 style="font-size:13px;text-transform:uppercase;letter-spacing:0.5px;color:#666;margin:16px 0 8px;font-weight:700;">Sources cit&eacute;es</h2>
    <ul style="margin:0 0 0 0;padding-left:20px;font-size:13px;color:#555;line-height:1.6;">
      {sources_html}
    </ul>
  </td></tr>

  <tr><td style="padding:20px 28px;">
    <div style="background:#fff7ed;border:1px solid #fdba74;padding:14px 18px;border-radius:8px;">
      <h3 style="margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;color:#ea580c;font-weight:700;">⚠ Points signal&eacute;s par Claude</h3>
      <ul style="margin:0;padding-left:18px;font-size:13px;color:#555;line-height:1.6;">
        {warnings_html}
      </ul>
    </div>
  </td></tr>

  <tr><td style="padding:24px 28px 28px;background:#f8f8f8;border-top:1px solid #e5e5e5;">
    <p style="margin:0 0 10px;font-size:12px;color:#666;line-height:1.5;">
      Article auto-publi&eacute; chaque lundi matin. Si tu rep&egrave;res des erreurs ou que le ton ne te pla&icirc;t pas, dis-le-moi &mdash; j'ajusterai le prompt pour les prochaines semaines.
    </p>
    <p style="margin:0;font-size:11px;color:#aaa;">Archive markdown : <code style="background:#fff;padding:2px 6px;border-radius:4px;font-size:10px;">DRAFTS/business/{datetime.now(PARIS_TZ).strftime("%Y-%m-%d")}.md</code></p>
  </td></tr>

</table>
</td></tr></table>
</body></html>'''

    payload = {
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to": [{"email": EMAIL_RECIPIENT, "name": "Stephen"}],
        "subject": f"✓ Business Officine publie - {today}",
        "htmlContent": html,
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{BREVO_API_BASE}/smtp/email",
            data=data,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            print(f"  [EMAIL] Envoye a {EMAIL_RECIPIENT} (messageId: {result.get('messageId', '?')})")
    except Exception as e:
        print(f"  [EMAIL-ERR] {e}")


def main():
    print("=== Pharm'Actus - Business Officine Hebdo ===")
    print(f"  Date: {datetime.now(PARIS_TZ).strftime('%Y-%m-%d %H:%M')}")

    print("\n[1/5] Collecte RSS...")
    articles = fetch_rss_articles()
    if not articles:
        print("  Aucun article. Arret.")
        return

    print("\n[2/5] Selection + redaction via Claude...")
    article = generate_business_article(articles)
    if not article:
        print("  Echec de la generation. Arret.")
        return
    print(f"  Titre : {article['titre']}")
    print(f"  Confidence : {article.get('confidence_score', 0)*100:.0f}%")

    print("\n[3/5] Sauvegarde archive markdown...")
    save_archive(article)

    print("\n[4/5] Publication directe sur le site...")
    article_id = publish_article_to_site(article)
    if not article_id:
        print("  Publication echouee. Email quand meme envoye pour info.")
        article_id = ""

    print("\n[5/5] Envoi email d'info...")
    send_published_email(article, article_id)

    print("\n=== Business Officine publie ===")
    print(f"URL : https://actus.pharmalpha.fr/articles/{article_id}.html")


if __name__ == "__main__":
    main()
