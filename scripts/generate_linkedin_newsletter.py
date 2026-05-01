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

    non_lsv = sorted(
        [a for a in recent if a.get("categorie") != "lsv"],
        key=score,
        reverse=True,
    )[:5]

    lsv_candidates = [a for a in recent if a.get("categorie") == "lsv"]
    lsv_candidates.sort(key=article_date, reverse=True)
    lsv = lsv_candidates[0] if lsv_candidates else None

    # Trier les 5 actus par date desc (la plus recente en premier)
    non_lsv.sort(key=article_date, reverse=True)

    return non_lsv, lsv


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

=== FORMAT EXACT (a respecter scrupuleusement) ===

Le format est tres specifique : alternance de blocs texte (avec **Unicode bold sans-serif** : 𝗔𝗕𝗖 𝗮𝗯𝗰 𝟬𝟭𝟮) et d'images. C'est le format LinkedIn Newsletter natif.

Caracteres Unicode bold a utiliser (mathematical sans-serif bold) :
- A-Z : 𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭
- a-z : 𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇
- 0-9 : 𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵
- Apostrophe et caracteres accentues NON convertis (rester en texte normal)

=== TON STYLE ===
- Tutoiement systematique
- Phrases courtes, percutantes
- Hook fort en intro
- Chaque actu finit par une fleche "→" suivie d'un takeaway actionnable
- Decontracte mais expert
- Public : pharmaciens titulaires + adjoints + preparateurs

=== REGLE LEGALE CRITIQUE (L.5122 - publicite Rx interdite) ===
INTERDICTION ABSOLUE de "merch", "promotion", "mise en avant", "vitrine", "lineaire" sur un medicament a prescription identifie (GLP-1 type Ozempic/Wegovy/Mounjaro, antibiotiques, antidiabetiques, antihypertenseurs, antidepresseurs, tout Rx rembourse).

Pour les Rx, angles autorises : impact macro/sante publique, reglementaire (AMM, LFSS, prix), formation equipes, gestion approvisionnement. JAMAIS d'angle commercial sur le produit.

Le merch / mise en avant n'est OK QUE pour : OTC, parapharmacie, complements alim, dispositifs medicaux non rembourses, ou les SERVICES officinaux.

=== ARTICLES DE LA SEMAINE ===
{actus_text}

{lsv_text}

=== CONTEXTE ===
- Numero : Semaine W{week_num} ({week_start.strftime('%d')}-{week_end.strftime('%d %B %Y')})
- A publier le : {monday_next.strftime('%A %d %B %Y')} matin
- Deja ~4000 abonnes a la newsletter LinkedIn

=== STRUCTURE A GENERER ===

Tu dois retourner un MARKDOWN complet exactement structure comme suit :

```markdown
# Newsletter LinkedIn "Pharm'Actus" — Semaine W{week_num} (XX-XX MOIS YYYY)

**À publier lundi XX MOIS matin (créneau 7h30-8h30)**

> **Format LinkedIn** : Article > "Publier dans Pharm'Actus"
> **Image de couverture** : à choisir parmi les 5 actus, ou logo Pharm'Actus

---

## TITRE de la newsletter (LinkedIn limite à ~80 caractères)

```
Pharm'Actus — [titre punchy de la semaine, max 80 char]
```

## SOUS-TITRE optionnel

```
[chiffre/insight] [chiffre/insight] [chiffre/insight] — 7 jours, 5 actus à retenir.
```

---

## 📰 CORPS DE LA NEWSLETTER

> **Mode d'emploi** : LinkedIn ne permet pas de coller texte+image en un seul collage. Tu colles le **bloc texte 1**, tu insères la **photo 01**, tu colles le **bloc texte 2**, tu insères la **photo 02**, etc.

---

### 🅐 BLOC TEXTE 1 — Intro (à coller en premier)

```
[Hook fort en Unicode bold]

[2-3 phrases d'intro courtes]

Voici ce que je retiens des 7 derniers jours, et pourquoi tu devrais y prêter attention.
```

### 📸 INSÉRER → `01_[slug_court_de_actu_1].jpg`

### 🅑 BLOC TEXTE 2 — Actu 1

```
━━━━━━━━━━━━━━━━━━━━

𝟭. [TITRE ACTU 1 EN UNICODE BOLD, ENTRE 60 ET 80 CARACTERES]

[2-3 phrases courtes qui presentent l'info, en texte normal]

→ [Takeaway actionnable, en texte normal, demarre par "Si...", "Traduction", "Concrètement", etc.]

📰 Lire l'analyse complète : [URL Pharm'Actus de cet article]
🔗 Source : [Nom source] — [URL source originale, si presente]
```

### 📸 INSÉRER → `02_[slug_court_de_actu_2].jpg`

### 🅒 BLOC TEXTE 3 — Actu 2
[meme structure]

### 📸 INSÉRER → `03_[slug_court_de_actu_3].jpg`

### 🅓 BLOC TEXTE 4 — Actu 3
[meme structure]

### 📸 INSÉRER → `04_[slug_court_de_actu_4].jpg`

### 🅔 BLOC TEXTE 5 — Actu 4
[meme structure]

### 📸 INSÉRER → `05_[slug_court_de_actu_5].jpg`

### 🅕 BLOC TEXTE 6 — Actu 5
[meme structure]

### 📸 INSÉRER → `06_LSV_[slug].jpg`

### 🅖 BLOC TEXTE 7 — Saviez-vous + clôture (à coller en dernier)

```
━━━━━━━━━━━━━━━━━━━━

🧠 𝗟𝗲 "𝗦𝗮𝘃𝗶𝗲𝘇-𝘃𝗼𝘂𝘀 ?" 𝗱𝗲 𝗹𝗮 𝘀𝗲𝗺𝗮𝗶𝗻𝗲

𝗟𝗲 𝘀𝗮𝘃𝗶𝗲𝘇-𝘃𝗼𝘂𝘀 ? [titre LSV en Unicode bold, court]

[Resume LSV en 3-4 phrases courtes en texte normal, avec quelques mots cles en Unicode bold]

Morale : [1 phrase qui fait reflexion, en texte normal]

📰 Histoire complète : [URL Pharm'Actus du LSV]

━━━━━━━━━━━━━━━━━━━━

✅ 𝗖𝗲 𝗾𝘂'𝗶𝗹 𝗳𝗮𝘂𝘁 𝗿𝗲𝘁𝗲𝗻𝗶𝗿 𝗱𝗲 𝗹𝗮 𝘀𝗲𝗺𝗮𝗶𝗻𝗲 :

→ [3 takeaways courts en texte normal]

━━━━━━━━━━━━━━━━━━━━

📬 𝗧𝘂 𝘃𝗲𝘂𝘅 𝗹'𝗮𝗰𝘁𝘂 𝗽𝗵𝗮𝗿𝗺𝗮 𝗰𝗵𝗮𝗾𝘂𝗲 𝗺𝗮𝘁𝗶𝗻 ?

Pour ne rien manquer chaque jour, abonne-toi à 𝗣𝗵𝗮𝗿𝗺'𝗔𝗰𝘁𝘂𝘀 → 𝗮𝗰𝘁𝘂𝘀.𝗽𝗵𝗮𝗿𝗺𝗮𝗹𝗽𝗵𝗮.𝗳𝗿

5 actus pharma + 1 "Saviez-vous ?" tous les matins, en 2 minutes de lecture.

━━━━━━━━━━━━━━━━━━━━

𝗘𝘁 𝘁𝗼𝗶, 𝗾𝘂𝗲𝗹𝗹𝗲 𝗮𝗰𝘁𝘂 𝘁'𝗮 𝗹𝗲 𝗽𝗹𝘂𝘀 𝗶𝗻𝘁𝗲𝗿𝗽𝗲𝗹𝗹𝗲́ 𝗰𝗲𝘁𝘁𝗲 𝘀𝗲𝗺𝗮𝗶𝗻𝗲 ?

Réponds en commentaire, je lis tout.
```

## Hashtags (en commentaire 1 min après publication, PAS dans la newsletter)

```
#pharmacie #officine #pharmaactu
```
```

=== INSTRUCTIONS FINALES ===

1. Genere le markdown complet ci-dessus, en remplaçant tous les [placeholders] par du contenu réel basé sur les articles de la semaine.
2. Numerote bien 1. à 5. les actus avec UNICODE BOLD pour les chiffres (𝟭. 𝟮. 𝟯. 𝟰. 𝟱.)
3. Les titres d'actus doivent etre en UNICODE BOLD complet (lettres + chiffres + ponctuation NON accentuee).
4. Les images sont nommees 01_xxx.jpg jusqu'a 06_LSV_xxx.jpg. Le slug doit etre court (3-5 mots, snake_case).
5. RESPECTE LA REGLE L.5122 : zero merch sur Rx.
6. Utilise des "→" (fleche pleine) pour les takeaways.
7. Utilise "━━━━━━━━━━━━━━━━━━━━" comme separateur entre les blocs (20 caracteres ━).
8. **OBLIGATOIRE pour CHAQUE actu et le LSV** : ajoute en bas du bloc, en derniere ligne :
   - "📰 Lire l'analyse complète : [URL Pharm'Actus exacte fournie dans les donnees]"
   - "🔗 Source : [Nom de la source] — [URL source originale]" (omettre cette ligne si pas d'URL source pour le LSV ou si l'article n'a pas d'URL externe)
   Les URLs doivent etre les VRAIES URLs fournies plus haut dans les donnees, pas inventees.

Retourne UNIQUEMENT le markdown complet, rien d'autre. Pas de preambule, pas de conclusion."""

    response = claude_create(
        client,
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
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
    """Build Brevo email attachments with images numbered 01-06."""
    attachments = []
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
            name = f"06_LSV_{slug}.jpg"
            content = fetch_image_as_base64(img_url)
            if content:
                attachments.append({"name": name, "content": content})
                print(f"  [IMG] {name}")
    return attachments


def send_newsletter_email(markdown, actus, lsv):
    """Send the newsletter draft by email with images attached."""
    api_key = os.environ.get("BREVO_API_KEY", "")
    if not api_key:
        print("  [SKIP] BREVO_API_KEY non definie")
        return

    today = datetime.now(PARIS_TZ)
    week_num = today.isocalendar()[1]
    monday_next = today + timedelta(days=(7 - today.weekday()) % 7 or 7)

    # HTML wrapper around the markdown (preformatted, copyable)
    md_escaped = markdown.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

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


def main():
    print("=== Newsletter LinkedIn Hebdo - Pharm'Actus ===")
    today = datetime.now(PARIS_TZ)
    print(f"  Date: {today.strftime('%Y-%m-%d %H:%M')} (Semaine W{today.isocalendar()[1]})")

    print("\n[1/4] Chargement articles.json...")
    articles = load_articles()
    print(f"  {len(articles)} articles charges")
    if not articles:
        print("  [ERROR] Aucun article. Arret.")
        return

    print("\n[2/4] Selection des articles de la semaine...")
    actus, lsv = select_week_articles(articles)
    print(f"  {len(actus)} actus selectionnees + {'1 LSV' if lsv else '0 LSV'}")
    for i, a in enumerate(actus, 1):
        print(f"  [{i}] {a.get('titre', '')[:70]} ({a.get('badge_label', '')})")
    if lsv:
        print(f"  [LSV] {lsv.get('titre', '')[:70]}")

    if len(actus) < 3:
        print("  [WARN] Moins de 3 actus disponibles, generation possiblement degradee")

    print("\n[3/4] Generation du markdown via Claude...")
    markdown = generate_newsletter_content(actus, lsv)
    print(f"  Markdown genere : {len(markdown)} caracteres")

    print("\n[4/4] Envoi email avec images attachees...")
    send_newsletter_email(markdown, actus, lsv)

    print("\n=== Termine ===")


if __name__ == "__main__":
    main()
