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


def md_to_html(text: str) -> str:
    """Convertit **bold** en <strong>bold</strong> et *italic* en <em>italic</em>.

    Bold avant italic (ordre important pour eviter collision patterns).
    """
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    return text


# ── Marque tendance ───────────────────────────────────────────────────

def load_trends_data():
    """Charge output/trends_daily.json si disponible. Retourne None sinon."""
    path = Path(__file__).parent.parent / "output" / "trends_daily.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _build_trends_site_block(data):
    """Génère la <section class="radar-pharmacien"> pour injection dans index.html.

    Tableau 4 colonnes : Pathologie | Evol. S-1 | Marque para | Evol. S-1
    Fenetre 7 jours glissants, mise a jour quotidienne.
    Retourne une chaine vide si data est None.
    """
    if not data:
        return ""

    patho_list  = data.get("pathologies", [])
    marque_list = data.get("soins", [])
    if not patho_list and not marque_list:
        return ""

    window_label = data.get("window_label", "")
    has_history  = data.get("has_history", False)

    def _delta_style(trend):
        if trend == "up":
            return "color:#15803d;font-weight:700;"
        if trend == "down":
            return "color:#dc2626;font-weight:700;"
        return "color:#9ca3af;font-weight:600;"

    rows_count = max(len(patho_list), len(marque_list))
    rows_html  = ""
    for i in range(rows_count):
        p = patho_list[i]  if i < len(patho_list)  else None
        m = marque_list[i] if i < len(marque_list) else None

        p_name  = p["display"]     if p else ""
        p_delta = p["delta_label"] if p else ""
        p_style = _delta_style(p["trend"] if p else "neutral")

        m_name  = m["display"]     if m else ""
        m_delta = m["delta_label"] if m else ""
        m_style = _delta_style(m["trend"] if m else "neutral")

        rows_html += (
            f'<tr style="border-bottom:1px solid #f3f4f6;">'
            f'<td style="padding:10px 14px;font-size:14px;color:#374151;">{p_name}</td>'
            f'<td style="padding:10px 10px;font-size:13px;text-align:right;{p_style}">{p_delta}</td>'
            f'<td style="padding:10px 14px;font-size:14px;color:#374151;'
            f'border-left:2px solid #f3f4f6;">{m_name}</td>'
            f'<td style="padding:10px 10px;font-size:13px;text-align:right;{m_style}">{m_delta}</td>'
            f'</tr>\n'
        )

    delta_source = data.get("delta_source", "")
    disclaimer = (
        '<p style="margin:10px 0 0;font-size:11px;color:#9ca3af;font-style:italic;">'
        '* Evol. S&#8209;1 : estimation via fenetre 14j — affinage a J+7 (historique).</p>'
        if delta_source == "proxy_14d_minus_7d" else ""
    )

    return (
        f'<section class="radar-pharmacien" aria-labelledby="rp-titre" '
        f'style="margin:32px 0;padding:24px;background:#fff;border-radius:12px;'
        f'border:1px solid #e5e7eb;box-shadow:0 1px 3px rgba(0,0,0,0.06);">'

        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">'
        f'<span style="display:inline-block;background:#0ea5e9;color:#fff;font-size:11px;'
        f'font-weight:700;padding:3px 10px;border-radius:100px;text-transform:uppercase;'
        f'letter-spacing:0.08em;">&#128225; Radar</span>'
        f'<h2 id="rp-titre" style="margin:0;font-size:17px;font-weight:700;color:#111118;">'
        f'Radar pharmacien'
        f'<span style="font-size:13px;font-weight:400;color:#6b7280;margin-left:8px;">'
        f'{window_label}</span>'
        f'</h2></div>'

        f'<p style="margin:0 0 16px;font-size:12px;color:#9ca3af;">'
        f'Requetes en forte hausse cette semaine en France &middot; '
        f'Decouverte automatique &middot; Mise a jour quotidienne</p>'

        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;min-width:400px;">'
        f'<thead><tr style="border-bottom:2px solid #e5e7eb;background:#f9fafb;">'
        f'<th style="padding:8px 14px;font-size:11px;font-weight:700;color:#6b7280;'
        f'text-transform:uppercase;letter-spacing:0.07em;text-align:left;">'
        f'Pathologie / Symptôme</th>'
        f'<th style="padding:8px 10px;font-size:11px;font-weight:700;color:#6b7280;'
        f'text-transform:uppercase;letter-spacing:0.07em;text-align:right;">Tendance</th>'
        f'<th style="padding:8px 14px;font-size:11px;font-weight:700;color:#6b7280;'
        f'text-transform:uppercase;letter-spacing:0.07em;text-align:left;'
        f'border-left:2px solid #e5e7eb;">Soin & Bien-être</th>'
        f'<th style="padding:8px 10px;font-size:11px;font-weight:700;color:#6b7280;'
        f'text-transform:uppercase;letter-spacing:0.07em;text-align:right;">Tendance</th>'
        f'</tr></thead>'
        f'<tbody>\n{rows_html}</tbody>'
        f'</table></div>'

        f'{disclaimer}'
        f'<p style="margin:12px 0 0;font-size:11px;color:#9ca3af;text-align:right;">'
        f'Source&nbsp;: Google Trends France (pytrends) &middot; 7 jours glissants</p>'
        f'</section>'
    )


def _build_trends_email_block(data):
    """Génère un bloc email table-based (compatible Outlook) — Radar pharmacien.

    Tableau 4 colonnes : Pathologie | Evol. | Marque para | Evol.
    Retourne une chaine vide si data est None.
    """
    if not data:
        return ""

    patho_list  = data.get("pathologies", [])
    marque_list = data.get("soins", [])
    if not patho_list and not marque_list:
        return ""

    window_label = data.get("window_label", "")

    def _color(trend):
        if trend == "up":   return "#15803d"
        if trend == "down": return "#dc2626"
        return "#9ca3af"

    rows_count = max(len(patho_list), len(marque_list))
    rows_html  = ""
    for i in range(rows_count):
        p = patho_list[i]  if i < len(patho_list)  else None
        m = marque_list[i] if i < len(marque_list) else None

        p_name  = p["display"]     if p else ""
        p_delta = p["delta_label"] if p else ""
        p_color = _color(p["trend"] if p else "neutral")

        m_name  = m["display"]     if m else ""
        m_delta = m["delta_label"] if m else ""
        m_color = _color(m["trend"] if m else "neutral")

        rows_html += (
            f'<tr style="border-bottom:1px solid #f3f4f6;">'
            f'<td style="padding:7px 12px;font-size:13px;color:#374151;">{p_name}</td>'
            f'<td style="padding:7px 8px;font-size:12px;font-weight:700;color:{p_color};'
            f'text-align:right;white-space:nowrap;">{p_delta}</td>'
            f'<td style="padding:7px 12px;font-size:13px;color:#374151;'
            f'border-left:2px solid #e5e7eb;">{m_name}</td>'
            f'<td style="padding:7px 8px;font-size:12px;font-weight:700;color:{m_color};'
            f'text-align:right;white-space:nowrap;">{m_delta}</td>'
            f'</tr>\n'
        )

    return (
        f'  <tr><td style="padding:20px 32px 0;">'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" '
        f'style="border-radius:8px;overflow:hidden;border:1px solid #e5e7eb;">'

        f'<tr><td style="background:#e0f2fe;padding:12px 16px;">'
        f'<p style="margin:0;font-family:\'Space Grotesk\',Arial,sans-serif;'
        f'font-size:13px;font-weight:700;color:#0284c7;letter-spacing:0.04em;">'
        f'&#128225;&nbsp; Radar pharmacien &mdash; {window_label}</p>'
        f'</td></tr>'

        f'<tr><td style="background:#ffffff;padding:0;">'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">'
        f'<tr style="background:#f9fafb;">'
        f'<th style="padding:6px 12px;font-size:10px;font-weight:700;color:#9ca3af;'
        f'text-align:left;text-transform:uppercase;letter-spacing:0.06em;">Pathologie / Symptôme</th>'
        f'<th style="padding:6px 8px;font-size:10px;font-weight:700;color:#9ca3af;'
        f'text-align:right;text-transform:uppercase;">Tendance</th>'
        f'<th style="padding:6px 12px;font-size:10px;font-weight:700;color:#9ca3af;'
        f'text-align:left;text-transform:uppercase;letter-spacing:0.06em;'
        f'border-left:2px solid #e5e7eb;">Soin & Bien-être</th>'
        f'<th style="padding:6px 8px;font-size:10px;font-weight:700;color:#9ca3af;'
        f'text-align:right;text-transform:uppercase;">Tendance</th>'
        f'</tr>'
        f'{rows_html}'
        f'</table></td></tr>'

        f'<tr><td style="background:#fafafa;padding:8px 16px;border-top:1px solid #f3f4f6;">'
        f'<p style="margin:0;font-family:\'Space Grotesk\',Arial,sans-serif;'
        f'font-size:11px;color:#9ca3af;">Google Trends France (pytrends) &middot; 7j glissants</p>'
        f'</td></tr>'

        f'</table></td></tr>'
        f'  <tr><td style="padding:20px 32px 0;">'
        f'<div style="border-top:1px solid #e5e5e5;"></div></td></tr>'
    )


# ── Expression du jour ────────────────────────────────────────────────

def get_expression_du_jour():
    """Return today's expression via a cyclic index based on the date.

    Start date: 2026-05-26 → index 0.
    Negative offset (before start_date) falls back to index 0.
    Returns None if the JSON file is missing or empty.
    """
    from datetime import date

    expr_file = Path(__file__).parent / "expressions_pharma.json"
    if not expr_file.exists():
        return None

    with open(expr_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    expressions = data.get("expressions", [])
    if not expressions:
        return None

    start_date = date(2026, 5, 26)
    today = date.today()
    idx = (today - start_date).days % len(expressions)
    if idx < 0:
        idx = 0

    return expressions[idx]


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
NEW_ARTICLES_PER_RUN = 4  # 1 pharma_france + 1 pharma_monde + 1 bonne_nouvelle + 1 avenir_pharma
# + 1 business_officine (generation separee en format long) + 1 LSV


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
                        "pratico_pratique": feed_cfg.get("pratico_pratique", False),
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


def curate_with_claude(raw_articles, existing_urls=None, excluded_categories=None):
    """Select and rewrite the best articles with Stephen's personal tone.

    excluded_categories: list of categories already covered by pending_actu
    injection — Claude will skip them and only fill the remaining slots.
    """
    excluded_categories = excluded_categories or []
    client = anthropic.Anthropic()

    # Filtrer en amont les articles deja publies sur le site
    if existing_urls:
        before = len(raw_articles)
        raw_articles = [a for a in raw_articles if a.get("link", "") not in existing_urls]
        skipped = before - len(raw_articles)
        if skipped:
            print(f"  {skipped} articles RSS deja publies, exclus de la curation")

    def _format_article(i, a):
        marker = " ⭐ PEPITE_PRATICO_PRATIQUE" if a.get("pratico_pratique") else ""
        return (
            f"[{i+1}]{marker} {a['title']}\n"
            f"Source: {a['source']} | Cat: {a['categorie']} | Date: {a['date']}\n"
            f"Resume: {a['summary']}\n"
            f"Lien: {a['link']}"
        )

    articles_text = "\n\n".join(_format_article(i, a) for i, a in enumerate(raw_articles))
    has_pratico = any(a.get("pratico_pratique") for a in raw_articles)

    today = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")

    # Build dynamic exclusion instruction (when a pending_actu already covers a category)
    cat_labels = {
        "pharma_france": "PHARMA FRANCE",
        "pharma_monde": "PHARMA MONDE",
        "bonne_nouvelle": "LA BONNE NOUVELLE",
        "avenir_pharma": "L'AVENIR DE LA PHARMA",
    }
    target_count = max(0, 4 - len(excluded_categories))
    exclusion_block = ""
    if excluded_categories:
        excluded_names = [cat_labels.get(c, c.upper()) for c in excluded_categories]
        exclusion_block = (
            "\n=== OVERRIDE EXCLUSION (LIRE AVANT TOUT) ===\n"
            f"La/les categorie(s) suivante(s) sont DEJA couverte(s) aujourd'hui par un article injecte manuellement (pepite PraticoPratique) :\n"
            f"- {', '.join(excluded_names)}\n"
            f"NE GENERE AUCUN article dans cette/ces categorie(s). Selectionne EXACTEMENT {target_count} articles dans les categories RESTANTES uniquement.\n"
            "Ignore les blocs '[X] OBLIGATOIRE' ci-dessous pour la/les categorie(s) exclue(s) — passe-les directement.\n"
            "=== FIN OVERRIDE ===\n"
        )

    pratico_block = ""
    if has_pratico and "pharma_france" not in excluded_categories:
        pratico_block = (
            "\n=== PRIORITE ABSOLUE PEPITE PRATICOPRATIQUE ===\n"
            "Si un ou plusieurs articles ci-dessous sont marques '⭐ PEPITE_PRATICO_PRATIQUE' (sources ANSM Informations de securite, ANSM Disponibilite/ruptures/rappels), ils ont PRIORITE ABSOLUE pour le slot [1] PHARMA FRANCE.\n"
            "Ces articles concernent : DHPC, rappels de lots, ruptures, alertes securite, modifications de formulation, retraits AMM. Ce sont des coms operationnelles ultra-utiles au comptoir.\n"
            "Choisis l'article PRATICO le plus impactant pour les pharmaciens (gros volume, large diffusion, action immediate au comptoir) et redige-le avec un angle 'voici ce qui change concretement pour toi demain matin' (CIP, dates, action attendue, ce qui change/ne change pas).\n"
            "Si AUCUN article PRATICO ne correspond clairement a une com PraticoPratique (ex: une simple actualite ANSM macro), reviens a la curation pharma_france classique.\n"
            "=== FIN PRIORITE PRATICO ===\n"
        )

    prompt = f"""Tu es Stephen, pharmacien consultant chez Pharm'Alpha et redacteur en chef de Pharm'Actus.
{exclusion_block}{pratico_block}

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

Selectionne et redige EXACTEMENT {target_count} articles dans les categories ci-dessous (1 article par categorie, ni plus ni moins, en sautant celles listees dans l'OVERRIDE EXCLUSION en haut s'il y en a) :

**[1] PHARMA FRANCE** (1 article OBLIGATOIRE) — Actu reglementaire/economique/metier francaise
- Impact direct sur l'exercice officinal : LFSS, conventions, ROSP, missions, marges, Ordre, ARS, HAS, ANSM, Assurance Maladie
- Source francaise uniquement (Moniteur, Quotidien du Pharmacien, Pharmacien de France, LEEM, HAS, ANSM, Egora, APMnews, Ordre, etc.)
- categorie : "pharma_france"
- badge_label : "Pharma France"

**[2] PHARMA MONDE** (1 article OBLIGATOIRE) — Actu internationale pharma/sante
- Source ETRANGERE uniquement (Reuters, STAT News, Pharmaceutical Journal, Fierce Pharma, European Pharmaceutical Review, Pharmacy Times, Nature Medicine, BioPharma Dive, etc.)
- Traduis et adapte en francais avec le style Stephen. Explique l'impact pour un pharmacien francais.
- categorie : "pharma_monde"
- badge_label : "Pharma Monde"

**[3] LA BONNE NOUVELLE** (1 article OBLIGATOIRE) — Une info positive et encourageante
- Avancee therapeutique, nouveau service valorise, remboursement obtenu, etude rassurante, innovation utile, humain derriere un chiffre
- Si aucune vraie bonne nouvelle dans les articles, prends la moins mauvaise et formule-la positivement
- categorie : "bonne_nouvelle"
- badge_label : "La bonne nouvelle"

**[4] L'AVENIR DE LA PHARMA** (1 article OBLIGATOIRE) — R&D, innovation, pipeline, perspectives
- Medicament en developpement (phase 2/3/4), nouvelle molecule, technologie emergente (ARNm, CAR-T, IA, etc.), recherche prometteuse avec impact clinique futur
- categorie : "avenir_pharma"
- badge_label : "L'avenir de la pharma"

NE PAS generer d'article categorie "sante" (cette categorie est desactivee). NE PAS generer d'article "business" (genere separement en format analytique long).

=== CHECKLIST FAITS OFFICINAUX SENSIBLES (OBLIGATOIRE avant toute affirmation) ===
Avant toute affirmation sur le cadre officinal francais, verifier mentalement :
- Qui paie quoi ? (Assurance Maladie / officine / patient / Etat) La reponse n'est JAMAIS symetrique entre medecins et pharmaciens.
- Qui remunere qui ? (forfait, remuneration a l'acte, dotation, honoraire de dispensation, majoration de coordination) Ces regimes sont distincts par profession.
- Quel est le statut conventionnel exact ? (avenant convention pharmacien, LFSS article precise, decret en Conseil d'Etat, arrete tarifaire) Citer l'acte reglementaire.
- NE JAMAIS inferer par symetrie medecin<->pharmacien : leurs statuts conventionnels, leurs modes de financement et leurs obligations sont FONDAMENTALEMENT DIFFERENTS.
  Exemple contre-indique : si un TROD ou une mission est gratuit pour le medecin (finance par l'AM dans son forfait), ce n'est PAS automatiquement gratuit pour l'officine (qui peut acheter les kits a sa charge ou etre rembourse differemment). Verifier la source originale.
- En cas de doute sur un fait chiffre, un financement ou un statut conventionnel : CITER TEXTUELLEMENT la source au lieu de reformuler. Ne pas paraphraser ce qu'on ne peut pas verifier.

REGLES DE SOURCES (STRICTES) :
1. REGLE ABSOLUE : JAMAIS 2 articles du meme media dans une meme journee. 1 seul Moniteur max, 1 seul Quotidien du Pharmacien max, etc. Si Pharma France choisit Moniteur, aucune autre categorie ne peut piocher dans Moniteur.
2. ALTERNANCE OBLIGATOIRE : Le Moniteur et Le Quotidien du Pharmacien sont des references mais NE DOIVENT PAS etre utilises TOUS les jours. Sur une semaine, varie au maximum. Alterne avec : Egora, HAS, Ordre des Pharmaciens, LEEM, Le Pharmacien de France, VIDAL, Sciences et Avenir, Pourquoi Docteur, APMnews, The Conversation, INSERM, ANSM, Medscape FR, etc.
3. Pour Pharma Monde : UNIQUEMENT des sources ETRANGERES (Reuters, STAT News, Pharmaceutical Journal, Fierce Pharma, European Pharmaceutical Review, Pharmacy Times, Nature Medicine, BioPharma Dive). Traduis en francais. Si aucune actu internationale claire dans les articles fournis, prends quand meme un article etranger et adapte-le au contexte francais.

=== IMPORTANCE DIFFERENCIANTE ===
Pharma Monde et Business Officine sont les 2 rubriques qui DIFFERENCIENT Pharm'Actus des autres newsletters pharma (qui se contentent de relayer Moniteur/Quotidien).
- Pharma Monde : NE DOIS JAMAIS etre loupee. C'est ce qui fait qu'un pharmacien francais va lire Pharm'Actus au lieu d'aller directement sur Moniteur.
- Business Officine est genere separement en format long et doit avoir le meme niveau d'exigence.
Donc : donne-toi a fond sur Pharma Monde. Pas d'article pharma monde faible ou evasif.

=== REGLE LEGALE CRITIQUE (a respecter ABSOLUMENT) ===
Code de la sante publique L.5122 : INTERDICTION de publicite/promotion grand public et de tout angle "merch" sur les medicaments a prescription (PMO/PMR), notamment :
- GLP-1 (Ozempic, Wegovy, Mounjaro, Trulicity, Saxenda...)
- Antibiotiques, antihypertenseurs, antidiabetiques, antidepresseurs, etc.
- Tout medicament rembourse par l'Assurance Maladie

INTERDIT pour tout article identifiant un Rx specifique :
- "Comment booster tes ventes de [Rx]"
- "Mise en avant en lineaire / vitrine / ILV"
- "Communication client" sur le produit
- "Merchandising" / "valoriser" / "promouvoir"

AUTORISE pour les Rx :
- Impact sante publique, acces aux soins
- Reglementation, AMM, taux de remboursement
- Formation des equipes, gestion approvisionnement
- Chiffres macro (CA national, impact sur le reseau)

Le merch / promotion commerciale n'est OK QUE pour : OTC, complements alimentaires, dermo-cosmetique, parapharmacie, dispositifs medicaux non rembourses, ou les SERVICES officinaux (vaccination, BPM, missions).

Pour chaque article, genere :
- "titre" : accrocheur, max 80 car, style direct de Stephen
- "resume" : 2-3 phrases percutantes, angle pharmacien
- "full_text" : 300-450 mots, 5-7 paragraphes separes par \\n\\n. Style Stephen : phrases courtes, chiffres concrets, impact officine, humour si pertinent. 1ere phrase = accroche forte. Ce texte est la version COMPLETE indexable par Google : developpe chaque argument, cite les chiffres cles, evite les formules vagues.
- "categorie" : voir ci-dessus
- "badge_label" : voir ci-dessus
- "source" et "source_url"
- "image_keywords" : 2-3 mots EN ANGLAIS pour chercher une photo libre de droit
- "tags" : ARRAY de 3 a 5 mots-cles thematiques en francais, minuscules, sans accents, format court (1-2 mots max par tag). Exemples : ["lfss", "remboursement", "vaccination", "rupture", "dp", "rosp", "marge", "substitution", "grippe", "covid", "diabete", "antibiotique", "generique", "galenique", "officine", "ars", "has", "ansm", "innovation", "recherche", "ia", "fda", "ema"]. Choisis les tags les plus specifiques au sujet pour permettre un filtrage precis.

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
    "tags": ["tag1", "tag2", "tag3"],
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
- Accroche percutante (VARIE les formulations, pas toujours "Tu savais que" ou "Figure-toi que")
- Anecdotes concretes : dates, noms, lieux, chiffres
- Un twist ou un fait surprenant au milieu du recit
- Conclusion qui fait le lien avec le quotidien au comptoir ou la medecine d'aujourd'hui
- Phrases courtes, rythmees, une idee par phrase
- Humour bienvenu, ton decontracte, tutoiement naturel

=== SUJETS POSSIBLES (pharmacie, medecine, sante en general — VARIER chaque jour) ===
IMPORTANT : ne te limite PAS a l'histoire de la pharmacie. Elargis a la medecine, la sante, la science.
Voici 15 categories a alterner jour apres jour :

1. Comment on diagnostiquait une maladie autrefois (diabete, syphilis, tuberculose, peste, etc.)
2. L'invention d'un instrument medical (stethoscope, thermometre, seringue, microscope, etc.)
3. Un medicament celebre et son histoire (aspirine, morphine, cortisone, viagra, etc.)
4. Une epidemie et comment on l'a vaincue (variole, cholera, polio, grippe espagnole, etc.)
5. Un medecin, chirurgien ou chercheur celebre/meconnu (pas que des pharmaciens !)
6. Une pratique medicale bizarre/terrifiante du passe (saignees, trepanation, mercure, etc.)
7. L'histoire d'un vaccin (qui l'a invente, comment, les resistances a l'epoque)
8. Un poison devenu medicament (ou l'inverse)
9. L'histoire d'une plante medicinale (du jardin au comprime)
10. Un record medical ou pharmaceutique insolite
11. L'evolution d'un outil du quotidien officinal (balance, mortier, ordonnance, etc.)
12. Une decouverte accidentelle en medecine (serendipite medicale)
13. L'histoire d'un organe ou d'une partie du corps et ce qu'on en croyait
14. Les debuts de la chirurgie, de l'anesthesie, de l'antisepsie
15. Une avancee recente mais meconnue de la science medicale

=== REGLE DE VARIETE (STRICTE) ===
- NE PAS toujours commencer le titre par "Quand les pharmaciens..." — ce format est trop repetitif
- Alterner les types de titres :
  * "Le saviez-vous ? Comment on diagnostiquait le diabete au XVIIe siecle"
  * "Le saviez-vous ? L'aspirine a failli ne jamais exister"
  * "Le saviez-vous ? Le stethoscope est ne de la pudeur d'un medecin"
  * "Le saviez-vous ? Pourquoi le mercure a ete le medicament le plus prescrit pendant 4 siecles"
  * "Le saviez-vous ? La premiere greffe du coeur a dure 18 minutes"
  * "Le saviez-vous ? Un pharmacien a invente le Coca-Cola (et c'etait pas pour boire)"
- VARIER les epoques : antiquite, moyen-age, renaissance, XVIIe-XVIIIe, XIXe, XXe, recent
- VARIER les domaines : pharmacie, chirurgie, diagnostic, epidemiologie, nutrition, psychiatrie, etc.

=== TITRES DEJA UTILISES (ne pas refaire un sujet trop proche) ===
{existing}

Genere UN SEUL "Le Saviez-Vous" original, sur un sujet DIFFERENT des titres ci-dessus.

JSON UNIQUEMENT :
{{
  "titre": "Le saviez-vous ? [titre accrocheur et VARIE, max 80 car]",
  "resume": "2-3 phrases de teaser percutantes",
  "full_text": "250-350 mots, 5-6 paragraphes separes par \\n\\n. Raconte l'histoire de facon captivante, style Stephen. Derniere phrase = lien avec la medecine/pharmacie d'aujourd'hui.",
  "image_keywords": "2-3 mots EN ANGLAIS pour photo libre de droit",
  "tags": ["histoire", "tag2", "tag3"],
  "date": "{today}"
}}

Pour les tags : 3 a 5 mots-cles thematiques en francais, minuscules, sans accents (ex: "histoire", "diagnostic", "diabete", "chirurgie", "vaccin", "plante", "chimie", "decouverte", "epidemie", "anesthesie", "instrument", "poison")."""

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


# ── CLAUDE : article Business Officine (analytique long format) ──────

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


def _factcheck_business_article(client, biz: dict) -> dict:
    """Second-pass Claude fact-check on a generated business_officine article.

    Detects incorrect inferences (e.g. medecin=pharmacien symmetry) and
    injects warnings into biz['warnings'] without modifying the article text
    (the human reviewer — Emilie — decides what to correct).

    Returns the enriched biz dict (may be unchanged if no issues found).
    """
    text_to_check = "\n\n".join(filter(None, [
        biz.get("chapo", ""),
        biz.get("contexte", ""),
        biz.get("analyse", ""),
        biz.get("recommandations", ""),
    ]))
    if not text_to_check.strip():
        return biz

    factcheck_prompt = f"""Tu es Emilie, juriste-reglementaire specialisee en droit pharmaceutique francais.
On te soumet un article "Business Officine" pour relecture AVANT publication.

=== ARTICLE A VERIFIER ===
{text_to_check}

=== TA MISSION ===
Relire chaque affirmation factuelle touchant :
1. Le financement et la remuneration de l'officine (qui paie quoi, combien, selon quel texte)
2. Les conventions pharmaciens (avenants, honoraires, ROSP, dotations, forfaits)
3. Les TROD, missions et actes pharmaceutiques (financement, statut conventionnel, prix)
4. Toute symetrie implicite avec le statut du medecin : les droits/obligations des pharmaciens NE SONT PAS un miroir de ceux des medecins.

Pour CHAQUE affirmation douteuse ou incorrecte que tu detectes, note :
- La phrase exacte problematique
- Ce qui est incorrect ou invérifiable
- Ce qu'il faudrait verifier ou corriger

Sois directe et precis. Si l'article est correct sur tous les points, reponds uniquement "RAS".

JSON UNIQUEMENT :
{{
  "issues_found": true|false,
  "warnings": [
    "FACT-CHECK: [phrase] → [probleme detecte / a verifier]"
  ]
}}

Si aucun probleme : {{"issues_found": false, "warnings": []}}"""

    try:
        response = claude_create(
            client,
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            messages=[{"role": "user", "content": factcheck_prompt}],
        )
        text = response.content[0].text.strip()
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            fc = json.loads(json_match.group())
            new_warnings = fc.get("warnings", [])
            if new_warnings:
                existing_warnings = biz.get("warnings", [])
                biz["warnings"] = existing_warnings + new_warnings
                biz["factcheck_issues"] = True
                print(f"  [FACTCHECK] {len(new_warnings)} probleme(s) detecte(s) par le second-pass")
                for w in new_warnings:
                    print(f"    - {w[:100]}")
            else:
                print("  [FACTCHECK] Second-pass OK, aucun probleme detecte")
    except Exception as e:
        # Le fact-check est non-bloquant : on logue et on continue
        print(f"  [FACTCHECK] Erreur second-pass (non bloquant): {e}")

    return biz


def generate_business_article(raw_articles, existing_urls=None, used_sources=None, used_titles=None):
    """Generate a daily Business Officine analytical article (long format).

    used_sources : list of source names already used TODAY by curate_with_claude.
    used_titles : list of article titles already used TODAY (to avoid same topic in business).
    """
    client = anthropic.Anthropic()
    used_sources = set(used_sources or [])
    used_titles = used_titles or []

    # Filter out already-published URLs
    if existing_urls:
        raw_articles = [a for a in raw_articles if a.get("link", "") not in existing_urls]

    # Filter out articles from sources already used today
    if used_sources:
        before = len(raw_articles)
        raw_articles = [a for a in raw_articles if a.get("source", "") not in used_sources]
        print(f"  {before - len(raw_articles)} articles exclus (sources deja utilisees aujourd'hui : {', '.join(used_sources)})")

    if not raw_articles:
        print("  [WARN] Aucun article business disponible apres filtrage des sources")
        return None

    # Prioritize business sources for the curation
    prioritized = sorted(raw_articles, key=lambda a: a.get("source", "") not in BUSINESS_PRIORITY_SOURCES)
    # Limit to top 30 to fit prompt
    prioritized = prioritized[:30]

    articles_text = "\n\n".join(
        f"[{i+1}] {a['title']}\nSource: {a['source']} | Date: {a['date']}\nResume: {a['summary']}\nLien: {a['link']}"
        for i, a in enumerate(prioritized)
    )

    today = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
    week_start = (datetime.now(PARIS_TZ) - timedelta(days=7)).strftime("%Y-%m-%d")

    used_sources_text = ""
    if used_sources:
        used_sources_text = (
            f"\n\n=== SOURCES DEJA UTILISEES AUJOURD'HUI (NE PAS reutiliser) ===\n"
            f"Les autres categories ont deja pris des articles dans : {', '.join(used_sources)}.\n"
            f"REGLE ABSOLUE : ne choisis AUCUN article provenant de ces sources. Pioche dans un autre media.\n"
        )
    if used_titles:
        used_sources_text += (
            f"\n=== SUJETS DEJA TRAITES AUJOURD'HUI (NE PAS refaire le meme sujet) ===\n"
            + "\n".join(f"- {t}" for t in used_titles) + "\n"
            + "L'article business DOIT porter sur un SUJET DIFFERENT de ceux ci-dessus. Pas de doublon thematique.\n"
        )

    prompt = f"""Tu es Stephen ROBERT, pharmacien consultant chez Pharm'Alpha et redacteur en chef de Pharm'Actus.

Tu rediges un article analytique quotidien "BUSINESS OFFICINE" publie chaque matin sur Pharm'Actus.{used_sources_text}

=== OBJECTIF DE LA RUBRIQUE ===
Donner aux pharmaciens titulaires une lecture BUSINESS claire d'une actu de la semaine :
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
- Conclus avec un insight actionable

=== CRITERES DE SELECTION DU SUJET ===
1. Sujet avec un VRAI impact business (pas juste une actu info)
2. Avec des chiffres publics verifiables
3. Qui touche la RENTABILITE, les MARGES, les MISSIONS, la REGLEMENTATION, ou le MARCHE
4. Idealement different des sujets traites dans les 4 autres categories du jour
5. EVITER un sujet deja traite les jours precedents (l'article doit etre original)

=== IMPORTANCE STRATEGIQUE ===
Business Officine est l'une des 2 RUBRIQUES DIFFERENCIANTES de Pharm'Actus (avec Pharma Monde).
C'est CE qui fait que les pharmaciens s'abonnent et partagent. Il NE DOIT JAMAIS etre loupe.
Si aucun angle business evident n'emerge de l'actu, extrais la dimension business d'un sujet reglementaire, economique ou structurel.
Donne-toi a fond sur cet article : chiffres precis, comparaisons, ton consultant.

=== CHECKLIST FAITS OFFICINAUX SENSIBLES (OBLIGATOIRE avant toute affirmation) ===
Avant toute affirmation sur le cadre officinal francais, verifier :
- Qui paie quoi ? (Assurance Maladie / officine / patient) La reponse n'est JAMAIS symetrique entre professions de sante.
- Qui remunere qui ? (forfait, honoraire de dispensation, dotation, ROSP, avenant convention) Ces regimes sont distincts par profession.
- Quel statut conventionnel exact s'applique ? Citer l'acte reglementaire (avenant, LFSS, decret, arrete tarifaire).
- NE JAMAIS inferer par symetrie medecin<->pharmacien. Exemple : un TROD gratuit pour le medecin (inclus dans son forfait AM) peut tres bien etre achete a sa charge par l'officine ou rembourse selon un mecanisme different. Verifier la source.
- En cas de doute sur un chiffre, un financement ou un statut conventionnel : CITER TEXTUELLEMENT la source officielle. Ne pas reformuler ce qu'on ne peut pas garantir.

=== REGLE LEGALE CRITIQUE (PUBLICITE Rx INTERDITE - L.5122) ===
INTERDICTION ABSOLUE de proposer des recommandations type "merch", "mise en avant", "promotion", "communication client", "vitrine", "linéaire", "ILV" sur un MEDICAMENT A PRESCRIPTION identifie (GLP-1 type Ozempic/Wegovy/Mounjaro, antibiotiques, antidiabetiques, antihypertenseurs, antidepresseurs, tout Rx rembourse par l'Assurance Maladie).

Si le sujet du jour est un Rx specifique, l'article business doit porter sur :
- Impact macro (CA national, evolution du marche, parts de marche labos)
- Reglementaire (AMM, LFSS, taux de remboursement, prix administre)
- Formation equipes / gestion approvisionnement (operationnel pas commercial)
- Pas de "comment booster tes ventes" / "comment valoriser ce produit"

Le merch / mise en avant n'est OK QUE pour : OTC, parapharmacie, dermo-cosmetique, complements alimentaires, dispositifs medicaux non rembourses, ou les SERVICES officinaux (vaccination, BPM, entretiens pharma).

Si tu identifies un risque, REFORMULE l'angle ou change de sujet.

=== ARTICLES DISPONIBLES ({week_start} → {today}) ===
{articles_text}

---

Parmi ces articles, identifie LE SUJET BUSINESS le plus percutant a traiter aujourd'hui. Redige un article analytique structure :

1. **titre** (max 90 car) : accrocheur, oriente business avec un chiffre si possible
2. **chapo** (2-3 phrases, ~40 mots) : le chiffre choc ou l'enjeu central
3. **contexte** (150-200 mots) : de quoi parle-t-on, depuis quand, qui est concerne
4. **analyse** (250-350 mots) : decryptage, chiffres precis, comparaisons, impact. AU MOINS 3 chiffres verifiables.
5. **recommandations** (100-150 mots) : 3-5 actions concretes numerotees (format "1. Titre — Detail")
6. **sources** : liste des sources utilisees avec nom + url
7. **image_keywords** : 2-3 mots EN ANGLAIS pour chercher une photo Pexels
8. **tags** : 4 tags en francais minuscules, sans accents

JSON UNIQUEMENT :
{{
  "titre": "...",
  "chapo": "...",
  "contexte": "...",
  "analyse": "...",
  "recommandations": "...",
  "sources": [
    {{"nom": "...", "url": "..."}}
  ],
  "image_keywords": "...",
  "tags": ["tag1", "tag2", "tag3", "tag4"],
  "confidence_score": 0.X,
  "warnings": ["liste des incertitudes / chiffres a verifier"]
}}

Le confidence_score (0-1) reflete ton niveau de certitude sur la qualite des chiffres."""

    response = claude_create(
        client,
        model="claude-sonnet-4-20250514",
        max_tokens=5000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    json_match = re.search(r"\{[\s\S]*\}", text)
    if not json_match:
        print("  [ERROR] Pas de JSON valide pour l'article business")
        return None

    try:
        biz = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        print(f"  [ERROR] JSON business parse: {e}")
        return None

    # Second-pass fact-check : Claude relit l'article business comme Emilie le ferait.
    biz = _factcheck_business_article(client, biz)

    # Assemble into the standard article format for downstream injection
    sources_list = biz.get("sources", [])
    sources_md = "\n".join(f"- {s.get('nom', '')}" for s in sources_list)

    full_text = (
        f"{biz.get('chapo', '')}\n\n"
        f"## Contexte\n\n{biz.get('contexte', '')}\n\n"
        f"## Analyse business\n\n{biz.get('analyse', '')}\n\n"
        f"## Recommandations actionnables\n\n{biz.get('recommandations', '')}\n\n"
        f"## Sources citees\n\n{sources_md}"
    )

    chapo = biz.get("chapo", "")
    resume = chapo[:280] + ("..." if len(chapo) > 280 else "")

    return {
        "titre": biz.get("titre", "Business Officine"),
        "resume": resume,
        "full_text": full_text,
        "categorie": "business_officine",
        "badge_label": "Business",
        "source": "Pharm'Actus",
        "source_url": "",
        "image_keywords": biz.get("image_keywords", "pharmacy business finance"),
        "tags": biz.get("tags", ["business", "analyse", "officine"]),
        "confidence_score": biz.get("confidence_score", 0),
        "warnings": biz.get("warnings", []),
        "sources_detail": sources_list,
    }


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
PENDING_ACTU_FILE = ROOT_DIR / "output" / "pending_actu.json"


# Mots-cles declenchant une review manuelle Emilie sur les articles officinaux sensibles.
# Logique : toute affirmation sur le financement, la remuneration ou le statut conventionnel
# officinal est susceptible d'etre incorrecte si Claude infere par symetrie medecin<->pharmacien.
OFFICINAL_SENSITIVE_KEYWORDS = {
    "convention", "conventionnel", "conventionnelle",
    "remuneration", "remunere", "remuneree",
    "honoraire", "honoraires",
    "rosp", "forfait", "dotation",
    "trod", "test rapide",
    "avenant",
    "marge officinale", "marge",
    "remboursement officine", "prise en charge",
    "assurance maladie finance", "assurance maladie prend en charge",
    "gratuit pour le pharmacien", "gratuit pour l'officine",
    "pharmacien prend en charge", "officine prend en charge",
    "lfss",
}


def flag_officinal_articles(articles, run_date: str) -> list[dict]:
    """Detect articles touching sensitive officinal facts and write a review file.

    An article is flagged if it belongs to 'business_officine' OR contains
    at least one keyword from OFFICINAL_SENSITIVE_KEYWORDS in its text fields.

    Returns the list of flagged articles (may be empty).
    Writes output/_REVIEW_EMILIE_{run_date}.json if any flagged articles found.
    """
    flagged = []
    for a in articles:
        is_business = a.get("categorie") == "business_officine"
        text_blob = " ".join([
            a.get("titre", ""),
            a.get("resume", ""),
            a.get("full_text", ""),
        ]).lower()
        has_keyword = any(kw in text_blob for kw in OFFICINAL_SENSITIVE_KEYWORDS)

        if is_business or has_keyword:
            flagged.append({
                "id": a.get("id", ""),
                "categorie": a.get("categorie", ""),
                "titre": a.get("titre", ""),
                "resume": a.get("resume", ""),
                "source": a.get("source", ""),
                "source_url": a.get("source_url", ""),
                "confidence_score": a.get("confidence_score"),
                "warnings": a.get("warnings", []),
                "flag_reason": "business_officine" if is_business else "keyword_match",
            })

    if flagged:
        review_dir = ROOT_DIR / "output"
        review_dir.mkdir(exist_ok=True)
        review_path = review_dir / f"_REVIEW_EMILIE_{run_date}.json"
        review_payload = {
            "generated_at": datetime.now(PARIS_TZ).isoformat(),
            "run_date": run_date,
            "instructions": (
                "Ces articles contiennent des affirmations sur le cadre officinal francais "
                "(financement, remuneration, convention, TROD, marge...). "
                "Verifier chaque fait avant publication ou envoyer la newsletter. "
                "En cas d'erreur detectee : corriger dans output/pending_actu.json "
                "ou notifier Stephen immediatement."
            ),
            "articles_to_review": flagged,
        }
        review_path.write_text(
            json.dumps(review_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  [REVIEW-EMILIE] {len(flagged)} article(s) flagge(s) → {review_path.name}")
    else:
        print("  [REVIEW-EMILIE] Aucun article a risque officinal detecte")

    return flagged


def get_fallback_photo(categorie):
    """Pick a stock fallback photo for the given category. Cycles through available photos."""
    # Business officine : single stock file, no numbering
    if categorie == "business_officine":
        photo_path = STOCK_DIR / "business_officine.jpg"
        if photo_path.exists():
            return "stock/business_officine.jpg"
        return ""

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


def load_pending_actus():
    """Load actus manually injected via output/pending_actu.json.

    Format accepted: a single article dict OR a list of dicts.
    Each article must contain at least titre/resume/full_text/categorie.
    Used for "PraticoPratique" pepites (com labos, recall, change formulation,
    ANSM alerts) that won't be picked up by RSS curation.
    """
    if not PENDING_ACTU_FILE.exists():
        return []
    try:
        data = json.loads(PENDING_ACTU_FILE.read_text(encoding="utf-8"))
        actus = data if isinstance(data, list) else [data]
        today = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
        for a in actus:
            a["date"] = today
            a.setdefault("categorie", "pharma_france")
            a.setdefault("badge_label", "Pharma France")
            a.setdefault("source", "Pharm'Alpha")
            a.setdefault("source_url", "")
            a.setdefault("tags", [])
        print(f"  [ACTU-PENDING] {len(actus)} actu(s) en attente injectee(s) : {actus[0].get('titre','')[:60]}...")
        return actus
    except Exception as e:
        print(f"  [ACTU-PENDING] Erreur: {e}")
        return []


# ── HTML : insertion des articles ─────────────────────────────────────

def get_existing_lsv_titles():
    """Extract ALL LSV titles from articles.json (historique complet, ~60+ jours)
    + fallback index.html (50 derniers articles seulement, ~8 jours).

    Pourquoi articles.json en priorite : index.html est limite a MAX_ARTICLES_TOTAL=50,
    soit ~8 jours d'historique LSV. Apres 10+ jours, Claude recycle les memes sujets
    (penicilline, cocaine, etc.). articles.json garde TOUT l'historique publie.
    """
    articles_json_path = ROOT_DIR / "articles.json"
    if articles_json_path.exists():
        try:
            data = json.loads(articles_json_path.read_text(encoding="utf-8"))
            articles = data.get("articles", [])
            lsvs = [
                a.get("titre", "") for a in articles
                if a.get("categorie") == "lsv" or a.get("id", "").startswith("lsv_")
            ]
            lsvs = [t for t in lsvs if t]
            if lsvs:
                return lsvs
        except Exception as e:
            print(f"  [WARN] articles.json illisible : {e}, fallback index.html")
    # Fallback : ancienne methode (limite 50 articles ~8 jours)
    html = INDEX_HTML.read_text(encoding="utf-8")
    return re.findall(r'titre:\s*"(Le saviez-vous[^"]*)"', html, re.IGNORECASE)


def _parse_entries(block: str) -> list:
    """Extract individual JS object literals from an ARTICLES array block.

    Uses brace-depth tracking (string-aware) so nested braces inside string
    values don't confuse the parser.
    """
    entries = []
    depth = 0
    entry_start = None
    in_str = False
    esc = False

    for i, c in enumerate(block):
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            if depth == 0:
                entry_start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and entry_start is not None:
                entries.append(block[entry_start:i + 1])
                entry_start = None

    return entries


def update_index_html(new_articles):
    """Insert new articles into index.html ARTICLES array.

    Multi-run safety: all existing articles whose date matches today are
    removed before the new batch is inserted.  A single pipeline run on
    a given day therefore always REPLACES the day's content instead of
    accumulating duplicate entries.
    """
    html = INDEX_HTML.read_text(encoding="utf-8")

    match = re.search(r"const ARTICLES = \[([\s\S]*?)\];", html)
    if not match:
        print("  [ERROR] ARTICLES array introuvable dans index.html")
        return False

    today = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")

    existing_block = match.group(1)

    # --- Purge today's articles (idempotent re-run) ---
    all_existing_entries = _parse_entries(existing_block)
    kept_entries = []
    purged = 0
    for entry in all_existing_entries:
        m = re.search(r'date:\s*"([^"]+)"', entry)
        if m and m.group(1) == today:
            purged += 1
        else:
            kept_entries.append(entry)

    if purged:
        print(f"  [DEDUP] {purged} article(s) du {today} purges avant re-insertion")
        # Rebuild existing_block without today's entries
        existing_block = "\n" + ",\n".join(kept_entries) + "\n" if kept_entries else ""

    # Recompute existing_ids / existing_urls from the purged block
    existing_ids = set(re.findall(r'id:\s*"([^"]+)"', existing_block))
    existing_urls = set(re.findall(r'source_url:\s*"([^"]+)"', existing_block))

    ASSETS_DIR.mkdir(exist_ok=True)

    new_js_entries = []
    actu_idx = 0

    for a in new_articles:
        # Skip if same source URL already exists (avoid duplicates across days)
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
        # No suffix loop needed: today's articles were purged above.
        # Keep the loop as a safety net only (e.g. duplicate LSV from pending).
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

        # Tags : array de strings, filtrage/normalisation
        raw_tags = a.get("tags", [])
        if isinstance(raw_tags, str):
            raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        clean_tags = []
        for t in raw_tags[:5]:
            if not isinstance(t, str):
                continue
            tag = t.strip().lower().replace(" ", "-")
            if tag and tag not in clean_tags:
                clean_tags.append(tag)
        a["tags"] = clean_tags
        tags_js = "[" + ", ".join(f'"{esc(t)}"' for t in clean_tags) + "]"

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
            f'    image_url: "{img_url}",\n'
            f'    tags: {tags_js}\n'
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

    # Inject "Expression du jour" banner.
    # The placeholder <!-- EXPRESSION_DU_JOUR --> only exists on the first run;
    # subsequent runs contain the rendered div — we replace it via regex.
    expr = get_expression_du_jour()
    if expr:
        def esc_html(s):
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        # md_to_html applied BEFORE esc_html so the generated <em>/<strong> tags
        # are not escaped. esc_html is only applied to plain-text fields (expression title).
        texte_html = md_to_html(expr["texte"])
        bandeau_html = (
            '<aside class="expression-du-jour" aria-label="Expression du jour : étymologie">'
            '<div class="expression-label">'
            '<svg class="expression-label-icon" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
            '<circle cx="7" cy="5" r="3.2" stroke="#4f46e5" stroke-width="1.3"/>'
            '<path d="M5.2 8.2 C4.2 9.8 4.8 12 7 12 C9.2 12 9.8 9.8 8.8 8.2" stroke="#4f46e5" stroke-width="1.3" stroke-linecap="round"/>'
            '<line x1="7" y1="1" x2="7" y2="2.1" stroke="#4f46e5" stroke-width="1.3" stroke-linecap="round"/>'
            '<line x1="9.5" y1="1.8" x2="8.7" y2="2.7" stroke="#4f46e5" stroke-width="1.3" stroke-linecap="round"/>'
            '</svg>'
            'Expression du jour'
            '</div>'
            f'<h2 class="expression-titre">{esc_html(expr["expression"])}</h2>'
            f'<p class="expression-corps">{texte_html}</p>'
            '</aside>'
        )
        # Replace existing rendered aside (regex) — handles re-runs after first injection.
        # Fallback: replace static placeholder comment (first run only).
        replaced, n = re.subn(
            r'<aside class="expression-du-jour"[^>]*>[\s\S]*?</aside>',
            bandeau_html,
            updated_html,
            count=1,
        )
        if n:
            updated_html = replaced
        else:
            # Legacy fallback: old div-based markup from before the redesign.
            replaced_legacy, n_legacy = re.subn(
                r'<div class="expression-bandeau">[\s\S]*?</div>\s*</div>\s*</div>',
                bandeau_html,
                updated_html,
                count=1,
            )
            if n_legacy:
                updated_html = replaced_legacy
            else:
                updated_html = updated_html.replace("<!-- EXPRESSION_DU_JOUR -->", bandeau_html, 1)

    # Injection section Marque tendance (après articles, avant archives CTA)
    trends_data = load_trends_data()
    trends_html = _build_trends_site_block(trends_data)
    if trends_html:
        if "<!-- MARQUE_TENDANCE -->" in updated_html:
            # Premier run ou placeholder explicite : remplace le commentaire
            updated_html = updated_html.replace("<!-- MARQUE_TENDANCE -->", trends_html, 1)
        else:
            # Runs suivants : remplace le bloc <section> existant
            updated_html, n = re.subn(
                r'<section class="(?:radar-pharmacien|marque-tendance)"[\s\S]*?</section>',
                trends_html,
                updated_html,
                count=1,
            )
            if not n:
                # Fallback : premier run sans placeholder — injecte avant archives CTA
                updated_html = updated_html.replace(
                    "<!-- ARCHIVES CTA -->",
                    f"{trends_html}\n\n<!-- ARCHIVES CTA -->",
                    1,
                )

    INDEX_HTML.write_text(updated_html, encoding="utf-8")

    print(f"  {len(new_js_entries)} articles ajoutes a index.html")

    # Generate individual article pages for social sharing
    generate_article_pages(new_articles)

    # Generate articles.json companion file (for archives.html)
    generate_articles_json(updated_html)

    return True


def generate_articles_json(index_html):
    """Parse ARTICLES array from index.html and write articles.json (for archives page)."""
    match = re.search(r"const ARTICLES = \[([\s\S]*?)\];", index_html)
    if not match:
        print("  [WARN] Impossible d'extraire ARTICLES pour articles.json")
        return
    block = match.group(1)

    # Parse JS-literal entries with balanced brace tracking (handles strings)
    entries = []
    depth = 0
    start = None
    in_str = False
    escape = False
    for i, c in enumerate(block):
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start is not None:
                entries.append(block[start:i + 1])
                start = None

    def js_entry_to_dict(js):
        """Convert a JS object literal to a Python dict. Fields are known: id, date, type, categorie, titre, resume, full_text, source, source_url, tiktok_url, badge_label, image_url, tags."""
        d = {}
        for field in ("id", "date", "type", "categorie", "titre", "resume", "full_text", "source", "source_url", "tiktok_url", "badge_label", "image_url"):
            m = re.search(rf'{field}:\s*"((?:[^"\\]|\\.)*)"', js)
            if m:
                val = m.group(1).replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
                d[field] = val
        # Tags : array of strings
        tm = re.search(r'tags:\s*\[([^\]]*)\]', js)
        if tm:
            tags_raw = tm.group(1)
            d["tags"] = [t.strip().strip('"') for t in re.findall(r'"([^"]*)"', tags_raw)]
        else:
            d["tags"] = []
        return d

    current_articles = [js_entry_to_dict(e) for e in entries]
    current_articles = [a for a in current_articles if a.get("id")]

    # Merge with existing articles.json (cumulative archive - articles never disappear)
    json_path = ROOT_DIR / "articles.json"
    existing_articles = []
    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as f:
                existing_data = json.load(f)
                existing_articles = existing_data.get("articles", [])
        except Exception as e:
            print(f"  [WARN] Lecture articles.json existant : {e}")

    # Purge today's articles from existing archive (idempotency: multi-run = no accumulation)
    today_str = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
    existing_articles = [a for a in existing_articles if a.get("date") != today_str]

    # Dedupe by id : les articles courants (fraîchement générés) priment sur l'historique
    current_ids = {a["id"] for a in current_articles}
    merged = list(current_articles)
    historical_count = 0
    for a in existing_articles:
        if a.get("id") and a["id"] not in current_ids:
            merged.append(a)
            historical_count += 1

    # Tri : date desc, puis actus avant LSV à date égale
    def sort_key(a):
        is_lsv = 1 if a.get("categorie") == "lsv" else 0
        return (a.get("date", ""), -is_lsv, a.get("id", ""))
    merged.sort(key=sort_key, reverse=True)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "articles": merged,
            "count": len(merged),
            "updated_at": datetime.now(PARIS_TZ).isoformat(),
        }, f, ensure_ascii=False, indent=2)
    print(f"  articles.json genere ({len(merged)} articles total : {len(current_articles)} depuis index.html + {historical_count} historiques)")


def _build_article_page_html(article_id: str, titre_raw: str, resume_raw: str, image_url: str, date_str: str, categorie: str, full_text_raw: str = "", source_url: str = "", source_name: str = "") -> str:
    """Build a single article stub HTML with full SEO metadata.

    The canonical and og:url both point to pharmalpha.fr/actus (Vercel target),
    not actus.pharmalpha.fr, to avoid duplicate signal during dual-push period.
    The meta-refresh is removed from <head>: the JS redirect at bottom of <body>
    handles UX for real visitors; Googlebot sees the full article body.
    full_text_raw: complete article body (300-500 words). Paragraphs separated by
    \n\n are each rendered as a <p>. If empty, falls back to resume.
    """
    titre = titre_raw.replace('"', "&quot;").replace("'", "&#39;")
    resume = resume_raw.replace('"', "&quot;").replace("'", "&#39;")

    # Meta description: resume truncated to 155 chars max
    meta_desc_raw = resume_raw.replace('"', "&quot;").replace("'", "&#39;")
    if len(meta_desc_raw) > 155:
        meta_desc = meta_desc_raw[:152] + "..."
    else:
        meta_desc = meta_desc_raw

    # OG image: prefer article image, fallback to default actus OG
    if image_url:
        og_image = f"https://actus.pharmalpha.fr/{image_url}"
    else:
        og_image = "https://pharmalpha.fr/assets/og-default-actus.png"

    # Canonical URL (Vercel target - avoids duplicate signal during dual-push)
    canonical_url = f"https://pharmalpha.fr/actus/articles/{article_id}.html"

    # Date ISO for schema (article date is YYYY-MM-DD, no time known)
    date_published = f"{date_str}T06:00:00+02:00" if date_str else ""
    date_modified = date_published  # no separate modified date available

    # Schema: map internal categorie to a human-readable articleSection
    section_map = {
        "pharma_france": "Pharmacie France",
        "pharma_monde": "Pharmacie Monde",
        "bonne_nouvelle": "Bonne Nouvelle",
        "avenir_pharma": "Avenir de la Pharmacie",
        "business_officine": "Business Officine",
        "lsv": "Le Saviez-Vous",
        "sante": "Sante",
    }
    article_section = section_map.get(categorie, "Pharmacie")

    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": titre_raw[:110],
        "description": resume_raw[:200],
        "datePublished": date_published,
        "dateModified": date_modified,
        "author": { "@id": "https://pharmalpha.fr/#stephen" },
        "publisher": { "@id": "https://pharmalpha.fr/#org" },
        "image": og_image,
        "articleSection": article_section,
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": canonical_url
        },
        "inLanguage": "fr-FR",
        "isPartOf": {
            "@type": "WebSite",
            "@id": "https://pharmalpha.fr/#website",
            "name": "Pharm'Actus",
            "url": "https://pharmalpha.fr/actus"
        }
    }

    import json as _json
    schema_json = _json.dumps(schema, ensure_ascii=False, indent=2)

    # Build article body HTML from full_text (paragraphs separated by \n\n).
    # Converts minimal Markdown: ## h2, ### h3, **bold**.
    # Falls back to empty string if no full_text provided (resume is already
    # rendered as article-lead above the body_html slot).
    def _para_to_html(para: str) -> str:
        """Convert a single paragraph (already stripped) to an HTML element."""
        import re as _re
        if para.startswith("### "):
            text = para[4:].strip()
            return f"  <h3>{text}</h3>"
        if para.startswith("## "):
            text = para[3:].strip()
            return f"  <h2>{text}</h2>"
        # Escape HTML special chars, then convert **bold**
        escaped = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        bolded = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        return f"  <p>{bolded}</p>"

    if full_text_raw and full_text_raw.strip():
        paras = [p.strip() for p in full_text_raw.split("\n\n") if p.strip()]
        # Skip first paragraph if it duplicates the resume (e.g. business_officine format)
        if paras and not paras[0].startswith("#") and paras[0][:80] == (resume_raw or "")[:80]:
            paras = paras[1:]
        body_html = "\n".join(_para_to_html(p) for p in paras)
    else:
        body_html = ""

    # Source link for footer attribution
    source_url_attr = source_url or "#"
    source_label = source_name or "Source"

    return f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titre} - Pharm'Actus</title>
<link rel="canonical" href="{canonical_url}" />
<meta name="description" content="{meta_desc}" />
<meta property="og:type" content="article" />
<meta property="og:title" content="{titre}" />
<meta property="og:description" content="{meta_desc}" />
<meta property="og:url" content="{canonical_url}" />
<meta property="og:image" content="{og_image}" />
<meta property="og:locale" content="fr_FR" />
<meta property="og:site_name" content="Pharm'Actus" />
<meta property="article:published_time" content="{date_published}" />
<meta property="article:author" content="https://pharmalpha.fr/stephen-robert" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{titre}" />
<meta name="twitter:description" content="{meta_desc}" />
<meta name="twitter:image" content="{og_image}" />
<script type="application/ld+json">
{schema_json}
</script>
</head>
<body>
<article>
  <h1>{titre}</h1>
  <p class="article-lead">{resume}</p>
  {body_html}
  <p><strong>Source :</strong> <a href="{source_url_attr}" rel="nofollow noopener">{source_label}</a></p>
  <footer class="article-footer">
    <p>Article redige par <a href="https://pharmalpha.fr/stephen-robert">Stephen Robert, Docteur en Pharmacie</a>.</p>
    <p>Decouvrir <a href="https://pharmalpha.fr/formations">les formations Pharm'Alpha</a>.</p>
  </footer>
</article>
</body>
</html>'''


def generate_article_pages(articles):
    """Generate individual HTML pages for each article with full SEO metadata."""
    articles_dir = ROOT_DIR / "articles"
    articles_dir.mkdir(exist_ok=True)

    for a in articles:
        article_id = a.get("id", "")
        if not article_id:
            continue

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


def _build_expression_email_block(expr):
    """Build a table-based email block for 'Expression du jour'.

    Uses only table/td layout (no flexbox) for maximum email client compat.
    Returns an empty string if expr is None.
    """
    if not expr:
        return ""

    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    # md_to_html BEFORE esc so <em>/<strong> tags survive; esc only on plain text fields.
    texte_html = md_to_html(expr["texte"])

    return f'''  <tr><td style="padding:20px 32px 0;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" style="margin-bottom:24px;">
      <tr>
        <td width="4" bgcolor="#4f46e5" style="background-color:#4f46e5;width:4px;">&nbsp;</td>
        <td width="12" style="width:12px;">&nbsp;</td>
        <td style="padding:18px 0;border:1px solid #e8e8ec;border-left:none;border-radius:0 6px 6px 0;background-color:#ffffff;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">
            <tr><td style="padding:0 20px 10px 20px;">
              <p style="margin:0;font-family:'Space Grotesk',Arial,sans-serif;font-size:10px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#4f46e5;line-height:1;">&#9673;&nbsp; Expression du jour</p>
            </td></tr>
            <tr><td style="padding:0 20px 10px 20px;">
              <h2 style="margin:0;font-family:'Space Grotesk',Arial,sans-serif;font-size:19px;font-weight:700;color:#111118;line-height:1.25;">
                {esc(expr["expression"])}
              </h2>
            </td></tr>
            <tr><td style="padding:0 20px 0 20px;">
              <p style="margin:0;font-family:'Space Grotesk',Arial,sans-serif;font-size:14px;line-height:1.65;color:#3a3a4a;">{texte_html}</p>
            </td></tr>
          </table>
        </td>
      </tr>
    </table>
  </td></tr>
  <tr><td style="padding:20px 32px 0;"><div style="border-top:1px solid #e5e5e5;"></div></td></tr>'''


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

    # Expression du jour email block (computed here so it's available in the f-string)
    expression_email_block = _build_expression_email_block(get_expression_du_jour())

    # Tendances email block (top 5, compact)
    trends_email_block = _build_trends_email_block(load_trends_data())

    return f'''<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{count_str} &mdash; {date_str}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
  <tr><td style="background:#ffffff;padding:28px 32px 16px;text-align:center;border-bottom:2px solid #f97316;">
    <a href="https://actus.pharmalpha.fr/" style="text-decoration:none;display:inline-block;"><img src="https://actus.pharmalpha.fr/assets/logo_pharmactus.png" alt="Pharm'Actus" width="280" style="max-width:280px;height:auto;display:block;border:0;margin:0 auto;" /></a>
    <div style="margin-top:10px;"><span style="font-size:13px;color:#888;letter-spacing:0.3px;">Chaque matin, retrouve l'actus pharma &agrave; lire entre deux ordo.</span></div>
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
  {expression_email_block}
  {articles_html}
  {trends_email_block}
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

INDEXNOW_KEY = "55aa442d1ea247c6bcada066b207629a"
INDEXNOW_HOST = "pharmalpha.fr"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"


def ping_indexnow(article_ids: list) -> None:
    """Notify IndexNow (Bing/Yandex/Copilot) of newly published article URLs.

    Sends a single batch POST with all new article URLs.
    IndexNow spec: https://www.indexnow.org/documentation
    Key file must be live at https://pharmalpha.fr/{INDEXNOW_KEY}.txt
    (deployed in pharmalpha-site root, served by Vercel).
    Non-blocking: logs result but never raises on failure.
    """
    if not article_ids:
        return

    urls = [
        f"https://{INDEXNOW_HOST}/actus/articles/{aid}.html"
        for aid in article_ids
    ]

    payload = {
        "host": INDEXNOW_HOST,
        "key": INDEXNOW_KEY,
        "keyLocation": f"https://{INDEXNOW_HOST}/{INDEXNOW_KEY}.txt",
        "urlList": urls,
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        INDEXNOW_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = resp.getcode()
            # 200 = accepted, 202 = queued (both OK per spec)
            if code in (200, 202):
                print(f"  [INDEXNOW] Ping OK ({code}) — {len(urls)} URL(s) soumises")
            else:
                print(f"  [INDEXNOW] Ping retourne HTTP {code} (inattendu)")
    except urllib.error.HTTPError as e:
        # 422 = URLs invalides, 429 = rate-limited, 403 = cle incorrecte/absente
        print(f"  [INDEXNOW] Erreur HTTP {e.code}: {e.reason} — verifier que le fichier cle est live sur pharmalpha.fr")
    except Exception as e:
        print(f"  [INDEXNOW] Echec ping (non bloquant): {e}")


def main():
    print("=== Pharm'Actus - Mise a jour quotidienne ===")
    print(f"  Date: {datetime.now(PARIS_TZ).strftime('%Y-%m-%d %H:%M')}")

    # 1. Fetch RSS
    print("\n[1/6] Collecte des flux RSS...")
    raw_articles = fetch_rss_articles()
    if not raw_articles:
        print("  Aucun article RSS. Arret.")
        return

    # 2.0 Charger les pending actus AVANT curation pour exclure leurs categories
    #     (cap newsletter a 6 cartes : 4 actus + 1 business + 1 LSV max).
    pending_actus = load_pending_actus()
    pending_categories = [a.get("categorie") for a in pending_actus if a.get("categorie")]

    # 2.1 Curate les slots restants
    existing_urls = get_existing_source_urls()
    target_count = max(0, 4 - len(pending_categories))
    print(f"\n[2/6] Curation via Claude ({len(raw_articles)} articles, {len(existing_urls)} deja publies, {target_count} slot(s) a remplir)...")
    if target_count > 0:
        curated = curate_with_claude(raw_articles, existing_urls, excluded_categories=pending_categories)
        print(f"  {len(curated)} articles selectionnes (hors business, LSV et pending)")
    else:
        curated = []
        print(f"  Aucun slot a remplir (pending_actus couvrent {len(pending_categories)} categories)")

    # 2.2 Prepend pending pour qu'ils apparaissent en tete (newsletter + site)
    if pending_actus:
        curated = pending_actus + curated
        print(f"  [ACTU-PENDING] {len(pending_actus)} actu(s) prependee(s) au curated")

    # Extraire les sources + sujets deja utilises pour eviter doublons dans business
    used_sources_today = [a.get("source", "") for a in curated if a.get("source")]
    used_titles_today = [a.get("titre", "") for a in curated if a.get("titre")]
    if used_sources_today:
        print(f"  Sources utilisees aujourd'hui : {', '.join(used_sources_today)}")

    # 3. Generate Business Officine analytical article (separate long-format call)
    print("\n[3/6] Generation de l'article Business Officine...")
    try:
        business = generate_business_article(raw_articles, existing_urls, used_sources=used_sources_today, used_titles=used_titles_today)
        if business:
            print(f"  Business: {business.get('titre', '')[:60]}...")
            print(f"  Confidence: {business.get('confidence_score', 0)*100:.0f}%")
            curated.append(business)
        else:
            print("  [WARN] Pas d'article business genere")
    except Exception as e:
        print(f"  [ERROR] Echec business: {e}")

    # 4. Generate 1 Le Saviez-Vous (ou utiliser le LSV en attente)
    print("\n[4/6] Generation du Le Saviez-Vous...")
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

    # 4.5 Flag articles officinaux sensibles pour review Emilie
    run_date = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
    print(f"\n[4.5/6] Verification articles officinaux sensibles...")
    flag_officinal_articles(curated, run_date)

    # 5. Photos + insertion HTML
    print("\n[5/6] Photos + mise a jour index.html...")
    updated = update_index_html(curated)

    if updated:
        # 6. Send newsletter (uniquement les articles effectivement ajoutes)
        added = [a for a in curated if a.get("id")]

        # 5.5 Ping IndexNow avec les URLs des nouveaux articles
        new_ids = [a["id"] for a in added if a.get("id")]
        if new_ids:
            print(f"\n[5.5/6] Ping IndexNow ({len(new_ids)} URL(s))...")
            ping_indexnow(new_ids)

        print(f"\n[6/6] Envoi newsletter Brevo ({len(added)} articles)...")
        send_newsletter(added)
        # Cleanup pending_actu.json apres usage reussi
        if PENDING_ACTU_FILE.exists():
            try:
                PENDING_ACTU_FILE.unlink()
                print("  [ACTU-PENDING] Fichier pending supprime apres utilisation")
            except Exception as e:
                print(f"  [ACTU-PENDING] Erreur suppression: {e}")
        print("\n=== Mise a jour terminee avec succes ===")
    else:
        print("\n=== Aucune mise a jour effectuee ===")


if __name__ == "__main__":
    main()
