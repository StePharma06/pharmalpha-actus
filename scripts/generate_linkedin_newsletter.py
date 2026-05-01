#!/usr/bin/env python3
"""
Pharm'Actus - Generateur Newsletter LinkedIn Hebdomadaire
========================================================

Chaque vendredi 7h Paris, prepare la newsletter LinkedIn hebdo de Stephen
au format exact du template W17 (Unicode bold + blocs texte/image alternes).

Workflow :
1. Charge articles.json (derniers 7 jours)
2. Selectionne les 5 meilleures actus + 1 LSV
3. Claude redige le markdown au format LinkedIn newsletter
4. Email a stephen.pharmacien@gmail.com avec :
   - Markdown copiable dans le corps
   - Images des articles en pieces jointes (ordre numero 01-06)
5. Stephen relit, ajuste si besoin, publie le LUNDI matin

REGLE CRITIQUE : pas de merch/promo sur Rx (GLP-1 etc) - L.5122

Usage:
  ANTHROPIC_API_KEY=sk-... BREVO_API_KEY=xkeysib-... python scripts/generate_linkedin_newsletter.py
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request
import base64
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

PARIS_TZ = ZoneInfo("Europe/Paris")
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
ARTICLES_JSON = ROOT_DIR / "articles.json"

LOOKBACK_DAYS = 7
SITE_URL = "https://actus.pharmalpha.fr"

BREVO_API_BASE = "https://api.brevo.com/v3"
SENDER_EMAIL = "actus@pharmalpha.fr"
SENDER_NAME = "Pharm'Actus Newsletter LinkedIn"
EMAIL_RECIPIENT = "stephen.pharmacien@gmail.com"

FALLBACK_MODEL = "claude-haiku-4-5-20251001"


def claude_create(client, **kwargs):
    """Call Claude API with retry + fallback to Haiku."""
    for attempt in range(2):
        try:
            return client.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            if e.status_code in (429, 529) and attempt < 1:
                print(f"  [RETRY] Claude {e.status_code}, attente 30s...")
                time.sleep(30)
            elif e.status_code in (429, 529):
                print(f"  [FALLBACK] bascule sur Haiku...")
                kwargs["model"] = FALLBACK_MODEL
                try:
                    return client.messages.create(**kwargs)
                except Exception:
                    raise e
            else:
                raise


def load_articles():
    """Load articles from articles.json."""
    if not ARTICLES_JSON.exists():
        print(f"[ERROR] {ARTICLES_JSON} introuvable")
        return []
    with open(ARTICLES_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("articles", [])


def select_week_articles(articles):
    """Select the 5 best non-LSV articles + 1 LSV from the past 7 days."""
    today = datetime.now(PARIS_TZ)
    cutoff = today - timedelta(days=LOOKBACK_DAYS)

    def article_date(a):
        try:
            return datetime.strptime(a.get("date", "1970-01-01"), "%Y-%m-%d").replace(tzinfo=PARIS_TZ)
        except Exception:
            return datetime(1970, 1, 1, tzinfo=PARIS_TZ)

    recent = [a for a in articles if article_date(a) >= cutoff]
    if not recent:
        # Fallback : prendre les plus recents disponibles
        recent = sorted(articles, key=article_date, reverse=True)[:20]

    # Scoring : differenciants en premier
    def score(a):
        cat = a.get("categorie", "")
        base = {
            "business_officine": 100,
            "pharma_monde": 70,
            "avenir_pharma": 60,
            "bonne_nouvelle": 40,
            "pharma_france": 30,
            "sante": 25,
            "lsv": 0,
        }.get(cat, 10)
        days_ago = (today - article_date(a)).days
        recency = max(0, 7 - days_ago)
        return base + recency

    # Diversifier : prendre 1 par categorie majeure si possible
    by_cat = {}
    for a in recent:
        cat = a.get("categorie", "")
        if cat == "lsv":
            continue
        if cat not in by_cat or score(a) > score(by_cat[cat]):
            by_cat[cat] = a

    # Categories prioritaires (1 de chaque si dispo)
    priority_cats = ["business_officine", "pharma_monde", "pharma_france", "bonne_nouvelle", "avenir_pharma"]
    selected = [by_cat[c] for c in priority_cats if c in by_cat]

    # Completer jusqu'a 6 avec les meilleurs scores restants
    used_ids = {a.get("id") for a in selected}
    remaining = sorted(
        [a for a in recent if a.get("categorie") != "lsv" and a.get("id") not in used_ids],
        key=score,
        reverse=True,
    )
    while len(selected) < 6 and remaining:
        selected.append(remaining.pop(0))

    # Tri final : date desc (plus recente en premier)
    selected.sort(key=article_date, reverse=True)
    selected = selected[:6]

    lsv_candidates = [a for a in recent if a.get("categorie") == "lsv"]
    lsv_candidates.sort(key=article_date, reverse=True)
    lsv = lsv_candidates[0] if lsv_candidates else None

    return selected, lsv


def generate_newsletter_content(actus, lsv):
    """Use Claude to generate the full newsletter markdown in W17 format."""
    client = anthropic.Anthropic()

    today = datetime.now(PARIS_TZ)
    week_num = today.isocalendar()[1]
    monday_next = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    week_start = today - timedelta(days=today.weekday())  # lundi de la semaine ecoulee
    week_end = week_start + timedelta(days=6)

    # Fournir les articles a Claude (avec liens Pharm'Actus + sources)
    actus_data = []
    for i, a in enumerate(actus, 1):
        actus_data.append({
            "n": i,
            "id": a.get("id", ""),
            "date": a.get("date", ""),
            "titre": a.get("titre", ""),
            "resume": a.get("resume", ""),
            "categorie": a.get("badge_label", ""),
            "full_text": a.get("full_text", "")[:1500],
            "source": a.get("source", "Pharm'Actus"),
            "source_url": a.get("source_url", ""),
            "pharmactus_url": f"{SITE_URL}/articles/{a.get('id', '')}.html" if a.get("id") else SITE_URL,
        })
    lsv_data = None
    if lsv:
        lsv_data = {
            "titre": lsv.get("titre", "").replace("Le saviez-vous ?", "").strip(),
            "resume": lsv.get("resume", ""),
            "full_text": lsv.get("full_text", "")[:1500],
            "pharmactus_url": f"{SITE_URL}/articles/{lsv.get('id', '')}.html" if lsv.get("id") else SITE_URL,
        }

    actus_text = "\n\n".join(
        f"[ACTU {a['n']}] {a['titre']} ({a['categorie']}, {a['date']})\n"
        f"Resume : {a['resume']}\n"
        f"Detail : {a['full_text']}\n"
        f"Source originale : {a['source']}" + (f" - {a['source_url']}" if a['source_url'] else " (pas d'URL externe)") + "\n"
        f"Lien Pharm'Actus : {a['pharmactus_url']}"
        for a in actus_data
    )
    lsv_text = (
        f"[LSV] {lsv_data['titre']}\nResume : {lsv_data['resume']}\nDetail : {lsv_data['full_text']}"
        if lsv_data else "(pas de LSV cette semaine)"
    )

    prompt = f"""Tu es Stephen ROBERT, pharmacien consultant, redacteur en chef de Pharm'Actus, influenceur LinkedIn (24K+ abonnes, ~4000 abonnes a la newsletter LinkedIn Pharm'Actus).

Tu rediges la newsletter LinkedIn HEBDOMADAIRE "Pharm'Actus" qui sera publiee le LUNDI matin.

=== FORMAT EXACT (matched a la version definitive de Stephen) ===

Format aere, SANS separateurs ━━━━ entre les blocs.
Utiliser **Unicode bold sans-serif** pour les titres et phrases d'accent.

Caracteres Unicode bold (mathematical sans-serif bold) :
- A-Z : 𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭
- a-z : 𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇
- 0-9 : 𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵
- Apostrophe et caracteres accentues : laisser tels quels (le caractere accentue 'é' ne se convertit pas)

=== TON STYLE ===
- Tutoiement systematique
- Phrases courtes, percutantes
- Decontracte mais expert
- Public : pharmaciens titulaires + adjoints + preparateurs
- Pas d'emoji 📰 🔗 dans les blocs (juste "Lire sur Pharm'Actus" et "Source")

=== REGLE LEGALE CRITIQUE (L.5122 - publicite Rx interdite) ===
INTERDICTION ABSOLUE de "merch", "promotion", "mise en avant", "vitrine", "lineaire" sur un medicament a prescription identifie (GLP-1, antibiotiques, antidiabetiques, antihypertenseurs, antidepresseurs, tout Rx rembourse).

Pour les Rx : angles autorises = impact macro/sante publique, reglementaire (AMM, LFSS, prix), formation equipes, gestion approvisionnement. JAMAIS d'angle commercial sur le produit.

Le merch / mise en avant n'est OK QUE pour : OTC, parapharmacie, complements alim, dispositifs medicaux non rembourses, ou les SERVICES officinaux.

=== ARTICLES DE LA SEMAINE ===
{actus_text}

{lsv_text}

=== CONTEXTE ===
- Numero : Semaine S{week_num} ({week_start.strftime('%d')}-{week_end.strftime('%d %B %Y')})
- A publier le : {monday_next.strftime('%A %d %B %Y')} matin
- Deja ~4000 abonnes a la newsletter LinkedIn

=== STRUCTURE A GENERER ===

Retourne le markdown complet ci-dessous. Le format est aere, SANS separateurs ━ entre les blocs.

```markdown
# Newsletter LinkedIn "Pharm'Actus" — Semaine S{week_num}

**À publier lundi matin (créneau 7h30-8h30 Paris)**

> Image de couverture : `00_cover.png` (en piece jointe)

---

## TITRE LinkedIn (max 80 chars)

```
Pharm'Actus — [titre punchy resumant la semaine]
```

## SOUS-TITRE

```
[2-3 chiffres/insights cles] — 7 jours, 6 actus a retenir.
```

---

## 📝 CORPS A COPIER DANS L'EDITEUR LINKEDIN

### Bloc 1 — Intro (à coller AVANT toute image)

```
[Hook puissant en Unicode bold, 1 phrase]

[2-3 phrases courtes qui presentent les sujets de la semaine, mots cles en Unicode bold].

Voici l'essentiel des 7 derniers jours, et pourquoi ca compte pour toi. Cette newsletter reprend les actus principales de la semaine derniere.

Pour garder un oeil sur ce type d'actus tous les jours, abonnez-vous sur https://actus.pharmalpha.fr/.

Bonne lecture !
```

### Image 01 → `01_[slug_actu_1].jpg`

### Bloc 2 — Actu 1

```
𝟭. [TITRE ACTU 1 EN UNICODE BOLD, GARDER LES ACCENTS NON-CONVERTIS]

[full_text de l'article EN ENTIER, paragraphes separes par sauts de ligne. Texte normal, ne pas raccourcir.]

Lire sur Pharm'Actus : [URL Pharm'Actus exact]

Source : [Nom de la source]
```

### Image 02 → `02_[slug_actu_2].jpg`

### Bloc 3 — Actu 2
[meme structure que Bloc 2]

### Image 03 → `03_[slug_actu_3].jpg`

### Bloc 4 — Actu 3
[meme structure]

### Image 04 → `04_[slug_actu_4].jpg`

### Bloc 5 — Actu 4
[meme structure]

### Image 05 → `05_[slug_actu_5].jpg`

### Bloc 6 — Actu 5
[meme structure]

### Image 06 → `06_[slug_actu_6].jpg`

### Bloc 7 — Actu 6
[meme structure]

### Image 07 → `07_lsv_[slug].jpg`

### Bloc 8 — Le Saviez-vous + Cloture

```
𝗟𝗲 𝗦𝗮𝘃𝗶𝗲𝘇-𝘃𝗼𝘂𝘀 ? [Titre LSV en Unicode bold, accents non convertis]

[full_text du LSV EN ENTIER, paragraphes separes par sauts de ligne. Mots cles en Unicode bold pour rythmer la lecture.]

Histoire complete sur Pharm'Actus : [URL Pharm'Actus du LSV]


𝗖𝗲 𝗾𝘂'𝗶𝗹 𝗳𝗮𝘂𝘁 𝗿𝗲𝘁𝗲𝗻𝗶𝗿 𝗱𝗲 𝗹𝗮 𝘀𝗲𝗺𝗮𝗶𝗻𝗲 :
→ [Takeaway 1, court, en texte normal]
→ [Takeaway 2, court]
→ [Takeaway 3, court]


𝗧𝘂 𝘃𝗲𝘂𝘅 𝗹'𝗮𝗰𝘁𝘂 𝗽𝗵𝗮𝗿𝗺𝗮 𝗰𝗵𝗮𝗾𝘂𝗲 𝗺𝗮𝘁𝗶𝗻 ?

Pour ne rien manquer chaque jour, abonne-toi a 𝗣𝗵𝗮𝗿𝗺'𝗔𝗰𝘁𝘂𝘀 → 𝗮𝗰𝘁𝘂𝘀.𝗽𝗵𝗮𝗿𝗺𝗮𝗹𝗽𝗵𝗮.𝗳𝗿

5 actus pharma + 1 "Saviez-vous ?" tous les matins, en 2 minutes de lecture.

𝗘𝘁 𝘁𝗼𝗶, 𝗾𝘂𝗲𝗹𝗹𝗲 𝗮𝗰𝘁𝘂 𝘁'𝗮 𝗹𝗲 𝗽𝗹𝘂𝘀 𝗶𝗻𝘁𝗲𝗿𝗽𝗲𝗹𝗹𝗲 𝗰𝗲𝘁𝘁𝗲 𝘀𝗲𝗺𝗮𝗶𝗻𝗲 ?

Reponds en commentaire, je lis tout.
```

## Hashtags (commentaire 1 min apres publication)

```
#pharmacie #officine #pharmaactu
```
```

=== INSTRUCTIONS FINALES ===

1. 6 ACTUS + 1 LSV. Pas 5, pas 7. Six actus.
2. Pour chaque actu, REPRODUIS l'INTEGRALITE du full_text fourni (ne raccourcis pas, ne resume pas).
3. Les TITRES d'actus en UNICODE BOLD (𝟭., 𝟮., etc. + lettres bold). Les caracteres accentues (é, è, à, ç) restent en texte normal.
4. Les LIENS sont les VRAIES URLs fournies, pas inventees.
5. Format AERE : pas de ━━━━ entre les blocs. Juste des sauts de ligne.
6. Pas d'emoji 📰 🔗 devant les liens : juste "Lire sur Pharm'Actus :" et "Source :".
7. L.5122 : ZERO merch sur Rx.
8. Le bloc 1 (intro) DOIT inclure litteralement la phrase :
   "Cette newsletter reprend les actus principales de la semaine derniere. Pour garder un oeil sur ce type d'actus tous les jours, abonnez-vous sur https://actus.pharmalpha.fr/. Bonne lecture !"

Retourne UNIQUEMENT le markdown complet, rien d'autre."""

    response = claude_create(
        client,
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text.strip()


def generate_companion_post(actus):
    """Genere le post LinkedIn 'feed' qui ANNONCE la newsletter (court, hook, 3 teasers).

    Publie sur le feed LinkedIn de Stephen 30-60 min apres la newsletter pour driver du trafic.
    Le LSV n'est pas teasé dans le post feed (trop long, on garde la priorite aux 3 actus impactantes).
    """
    client = anthropic.Anthropic()

    # Top 3 actus les plus impactantes (priorite Business + Pharma Monde)
    score_map = {
        "business_officine": 100, "pharma_monde": 70, "avenir_pharma": 60,
        "bonne_nouvelle": 40, "pharma_france": 30,
    }
    top3 = sorted(actus, key=lambda a: score_map.get(a.get("categorie", ""), 0), reverse=True)[:3]
    top3_text = "\n\n".join(
        f"[ACTU TOP {i+1}] {a.get('titre', '')} ({a.get('badge_label', '')})\n"
        f"Resume : {a.get('resume', '')}"
        for i, a in enumerate(top3)
    )

    prompt = f"""Tu es Stephen ROBERT, pharmacien consultant + influenceur LinkedIn (24K abonnes, ~4000 abonnes newsletter Pharm'Actus).

Tu rediges un POST LinkedIn court (PAS la newsletter, le post FEED qui l'annonce).

=== OBJECTIF ===
Ce post est publie sur ton feed normal LinkedIn 30-60 min APRES la newsletter, pour driver du trafic vers elle.
La newsletter apparait juste au-dessus du post (en epinglage de profil pour les abonnes).

=== STYLE STEPHEN (LinkedIn feed) ===
- Hook puissant en 1-2 lignes, en Unicode bold (𝗔𝗕𝗖 𝗮𝗯𝗰)
- Tutoiement
- 3 teasers d'actus importants (1-2 phrases chacun)
- Mots cles en Unicode bold pour rythmer
- Renvoi vers la newsletter avec "↑" (signifie : la newsletter est au-dessus)
- 1-2 hashtags max
- 800-1200 caracteres total

=== STRUCTURE ===

```
[Hook punchy 1-2 lignes en Unicode bold]

[Phrase d'introduction "Cette semaine..." ou similaire]

[Teaser actu 1 : 1-2 phrases avec un chiffre ou angle fort, mots cles en bold]

[Teaser actu 2 : idem]

[Teaser actu 3 : idem]

[Phrase de transition type "et 3 autres actus + le LSV qui fera scroller"]

📬 Tout est dans la newsletter Pharm'Actus que je viens de publier juste au-dessus ↑

[CTA d'abonnement a la newsletter]

#pharmacie #officine #pharmaactu
```

=== ARTICLES TOP 3 DE LA SEMAINE ===
{top3_text}

=== REGLE LEGALE L.5122 ===
Pas de merch/promo sur Rx (GLP-1 etc).

Genere le post complet, pret a copier sur LinkedIn. Retourne UNIQUEMENT le texte du post, rien d'autre."""

    response = claude_create(
        client,
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text.strip()


def fetch_image_as_base64(url):
    """Download an image from URL and return base64-encoded content."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; PharmActus/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return base64.b64encode(resp.read()).decode("utf-8")
    except Exception as e:
        print(f"  [IMG-ERR] {url}: {e}")
        return None


def build_email_attachments(actus, lsv):
    """Build Brevo email attachments : cover (00) + articles (01-06) + LSV (07)."""
    attachments = []
    # Cover image (00_cover.png)
    cover_b64 = generate_cover_image()
    if cover_b64:
        attachments.append({"name": "00_cover.png", "content": cover_b64})
        print(f"  [IMG] 00_cover.png")
    for i, a in enumerate(actus, 1):
        img_url = a.get("image_url", "")
        if not img_url:
            continue
        if not img_url.startswith("http"):
            img_url = f"{SITE_URL}/{img_url}"
        # Slug from title (3-5 words)
        slug = re.sub(r"[^a-z0-9]+", "_", a.get("titre", "").lower())[:40].strip("_")
        name = f"{i:02d}_{slug}.jpg"
        content = fetch_image_as_base64(img_url)
        if content:
            attachments.append({"name": name, "content": content})
            print(f"  [IMG] {name}")
    if lsv:
        img_url = lsv.get("image_url", "")
        if img_url:
            if not img_url.startswith("http"):
                img_url = f"{SITE_URL}/{img_url}"
            slug = re.sub(r"[^a-z0-9]+", "_", lsv.get("titre", "").lower())[:30].strip("_")
            name = f"07_lsv_{slug}.jpg"
            content = fetch_image_as_base64(img_url)
            if content:
                attachments.append({"name": name, "content": content})
                print(f"  [IMG] {name}")
    return attachments


def send_newsletter_email(markdown, actus, lsv, companion_post=""):
    """Send the newsletter draft by email with images attached + companion feed post."""
    api_key = os.environ.get("BREVO_API_KEY", "")
    if not api_key:
        print("  [SKIP] BREVO_API_KEY non definie")
        return

    today = datetime.now(PARIS_TZ)
    week_num = today.isocalendar()[1]
    monday_next = today + timedelta(days=(7 - today.weekday()) % 7 or 7)

    # HTML wrapper around the markdown (preformatted, copyable)
    md_escaped = markdown.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    companion_escaped = (companion_post or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    companion_section = ""
    if companion_post:
        companion_section = f'''
  <tr><td style="padding:8px 28px 0;">
    <h2 style="font-size:16px;margin:0 0 4px;color:#1a1a1a;">📱 Post LinkedIn associe (a publier 30-60 min APRES la newsletter sur ton feed normal)</h2>
    <p style="margin:0 0 12px;font-size:12px;color:#666;line-height:1.5;">Ce post court drive du trafic vers la newsletter. Il mentionne "↑" car la newsletter apparait au-dessus dans le feed des abonnes.</p>
  </td></tr>
  <tr><td style="padding:0 28px 28px;">
    <div style="background:#fff7ed;border:2px solid #f97316;border-radius:12px;padding:20px 22px;font-family:'Segoe UI',system-ui,sans-serif;font-size:14px;color:#1a1a1a;line-height:1.6;white-space:pre-wrap;word-wrap:break-word;user-select:all;">{companion_escaped}</div>
    <div style="text-align:right;font-size:11px;color:#aaa;margin-top:4px;">{len(companion_post)} caracteres</div>
  </td></tr>
'''

    html = f'''<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;color:#1a1a1a;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="780" cellpadding="0" cellspacing="0" style="max-width:780px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06);">

  <tr><td style="background:#0a66c2;padding:24px 28px;">
    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#cfe4ff;margin-bottom:6px;">📰 Newsletter LinkedIn Pharm'Actus &mdash; Semaine W{week_num}</div>
    <div style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">Brouillon pret pour Lundi matin</div>
    <div style="font-size:13px;color:#cfe4ff;margin-top:6px;">À publier le {monday_next.strftime('%A %d %B %Y')} matin (7h30-8h30)</div>
  </td></tr>

  <tr><td style="padding:20px 28px 12px;background:#fff7ed;border-bottom:1px solid #fdba74;">
    <p style="margin:0;font-size:13px;color:#92400e;line-height:1.5;">
      <strong>⚠️ Brouillon</strong> — Relis tout, ajuste si besoin. <strong>RIEN n'est publie automatiquement.</strong> Tu copies/colles bloc par bloc lundi matin sur LinkedIn.
    </p>
  </td></tr>

  <tr><td style="padding:24px 28px 8px;">
    <h2 style="font-size:16px;margin:0 0 8px;color:#1a1a1a;">📋 Procedure rapide</h2>
    <ol style="margin:0;padding-left:20px;font-size:13px;color:#555;line-height:1.7;">
      <li>LinkedIn → "Publier dans Pharm'Actus" (newsletter existante)</li>
      <li>Copie le <strong>TITRE</strong> et le <strong>SOUS-TITRE</strong> en haut</li>
      <li>Bloc Texte 1 → puis insère <strong>image 01</strong> (icone image LinkedIn)</li>
      <li>Bloc Texte 2 → puis insère <strong>image 02</strong></li>
      <li>... idem pour les blocs 3-6 et leurs images</li>
      <li>Bloc Texte 7 (cloture)</li>
      <li>Publie</li>
      <li>Commentaire 1min apres : <code>#pharmacie #officine #pharmaactu</code></li>
    </ol>
    <p style="margin:8px 0 0;font-size:12px;color:#888;">Les <strong>6 images</strong> sont en pieces jointes de cet email, nommees dans l'ordre.</p>
  </td></tr>

  <tr><td style="padding:16px 28px 28px;">
    <h2 style="font-size:16px;margin:0 0 12px;color:#1a1a1a;">📝 Markdown complet (a copier dans LinkedIn)</h2>
    <div style="background:#f8fafc;border:2px solid #0a66c2;border-radius:12px;padding:24px;font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;color:#1a1a1a;line-height:1.6;white-space:pre-wrap;word-wrap:break-word;user-select:all;">{md_escaped}</div>
  </td></tr>
{companion_section}
  <tr><td style="padding:20px 28px 24px;background:#f8f8f8;border-top:1px solid #e5e5e5;">
    <p style="margin:0;font-size:12px;color:#666;line-height:1.5;">
      Genere automatiquement chaque vendredi matin a partir des articles Pharm'Actus de la semaine ecoulee. Si le ton ou la selection ne te plait pas, dis-le moi - j'ajuste le prompt.
    </p>
  </td></tr>

</table>
</td></tr></table>
</body></html>'''

    payload = {
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to": [{"email": EMAIL_RECIPIENT, "name": "Stephen"}],
        "subject": f"📰 Newsletter LinkedIn W{week_num} - Brouillon pret pour lundi",
        "htmlContent": html,
    }

    # Attach images
    attachments = build_email_attachments(actus, lsv)
    if attachments:
        payload["attachment"] = attachments

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
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            print(f"  [EMAIL] Envoye a {EMAIL_RECIPIENT} (messageId: {result.get('messageId', '?')})")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        print(f"  [EMAIL-ERR] {e.code} {e.reason} : {body}")
    except Exception as e:
        print(f"  [EMAIL-ERR] {e}")


def generate_cover_image():
    """Generate a 1200x675 cover image with logo + week number. Returns base64 string or None."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        logo_path = ROOT_DIR / "assets" / "logo_pharmactus.png"
        if not logo_path.exists():
            return None
        W, H = 1200, 675
        bg = Image.new("RGB", (W, H), "#ffffff")
        draw = ImageDraw.Draw(bg)
        draw.rectangle([(0, 0), (W, 8)], fill="#f97316")
        draw.rectangle([(0, H - 8), (W, H)], fill="#f97316")
        logo = Image.open(logo_path).convert("RGBA")
        target_w = int(W * 0.65)
        ratio = target_w / logo.size[0]
        new_h = int(logo.size[1] * ratio)
        logo = logo.resize((target_w, new_h), Image.LANCZOS)
        logo_x = (W - target_w) // 2
        logo_y = int(H * 0.32) - new_h // 2
        bg.paste(logo, (logo_x, logo_y), logo)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 32)
        except Exception:
            font = ImageFont.load_default()
        week_num = datetime.now(PARIS_TZ).isocalendar()[1]
        sub = f"L'essentiel de la semaine pharma  ·  S{week_num}"
        bbox = draw.textbbox((0, 0), sub, font=font)
        draw.text(((W - (bbox[2] - bbox[0])) // 2, logo_y + new_h + 50), sub, fill="#1a1a1a", font=font)
        tag = "5 actus + 1 histoire pharma  ·  chaque matin sur actus.pharmalpha.fr"
        bbox = draw.textbbox((0, 0), tag, font=font)
        draw.text(((W - (bbox[2] - bbox[0])) // 2, H - 80), tag, fill="#888888", font=font)
        import io
        buf = io.BytesIO()
        bg.save(buf, "PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"  [COVER-ERR] {e}")
        return None


def main():
    print("=== Newsletter LinkedIn Hebdo - Pharm'Actus ===")
    today = datetime.now(PARIS_TZ)
    print(f"  Date: {today.strftime('%Y-%m-%d %H:%M')} (Semaine W{today.isocalendar()[1]})")

    print("\n[1/5] Chargement articles.json...")
    articles = load_articles()
    print(f"  {len(articles)} articles charges")
    if not articles:
        print("  [ERROR] Aucun article. Arret.")
        return

    print("\n[2/5] Selection des articles de la semaine...")
    actus, lsv = select_week_articles(articles)
    print(f"  {len(actus)} actus selectionnees + {'1 LSV' if lsv else '0 LSV'}")
    for i, a in enumerate(actus, 1):
        print(f"  [{i}] {a.get('titre', '')[:70]} ({a.get('badge_label', '')})")
    if lsv:
        print(f"  [LSV] {lsv.get('titre', '')[:70]}")

    if len(actus) < 3:
        print("  [WARN] Moins de 3 actus disponibles, generation possiblement degradee")

    print("\n[3/5] Generation du markdown newsletter via Claude...")
    markdown = generate_newsletter_content(actus, lsv)
    print(f"  Markdown genere : {len(markdown)} caracteres")

    print("\n[4/5] Generation du post LinkedIn associe (feed) via Claude...")
    try:
        companion_post = generate_companion_post(actus)
        print(f"  Post genere : {len(companion_post)} caracteres")
    except Exception as e:
        print(f"  [WARN] Echec post associe : {e}")
        companion_post = ""

    print("\n[5/5] Envoi email (newsletter + post associe + images + cover)...")
    send_newsletter_email(markdown, actus, lsv, companion_post=companion_post)

    print("\n=== Termine ===")


if __name__ == "__main__":
    main()
