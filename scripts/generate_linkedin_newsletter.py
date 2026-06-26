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

MONTHS_FR = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
             "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


def _strip_emdash(s):
    """Aucun tiret cadratin/demi-cadratin dans le contenu LinkedIn (regle Stephen :
    'on ne peut pas s'en separer ?'). Preserve les sauts de ligne."""
    if not isinstance(s, str):
        return s
    s = re.sub(r'(^|\n)[ \t]*[—–][ \t]*', r'\1- ', s)   # puce en debut de ligne
    s = re.sub(r'[ \t]*[—–][ \t]*', ' - ', s)            # em dash en ligne
    return s


def format_date_range_fr(start, end):
    """Formate une plage de dates en français: 'X au Y Mois YYYY' ou 'X Mois au Y Mois YYYY'."""
    if start.month == end.month:
        return f"{start.day} au {end.day} {MONTHS_FR[end.month]} {end.year}"
    else:
        return f"{start.day} {MONTHS_FR[start.month]} au {end.day} {MONTHS_FR[end.month]} {end.year}"


def _do_create(client, stream, kwargs):
    """Un seul appel Claude, en streaming (pour gros max_tokens) ou non."""
    if stream:
        # Streaming obligatoire au-dela de ~16K max_tokens (sinon timeout SDK).
        with client.messages.stream(**kwargs) as s:
            return s.get_final_message()
    return client.messages.create(**kwargs)


def claude_create(client, stream=False, **kwargs):
    """Call Claude API with retry + fallback to Haiku. stream=True pour les gros outputs."""
    for attempt in range(2):
        try:
            return _do_create(client, stream, kwargs)
        except anthropic.APIStatusError as e:
            if e.status_code in (429, 529) and attempt < 1:
                print(f"  [RETRY] Claude {e.status_code}, attente 30s...")
                time.sleep(30)
            elif e.status_code in (429, 529):
                print(f"  [FALLBACK] bascule sur Haiku...")
                kwargs["model"] = FALLBACK_MODEL
                try:
                    return _do_create(client, stream, kwargs)
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


def get_view_stats_week(from_date: str, to_date: str, limit: int = 20) -> list:
    """Recupere les articles les plus vus de la semaine depuis Supabase (best-effort)."""
    edge_url = "https://ibmqaybmhpzdlgyntzbs.supabase.co/functions/v1/actus-track-view"
    url = f"{edge_url}?from={from_date}&to={to_date}&limit={limit}"
    try:
        import urllib.request as _req
        with _req.urlopen(url, timeout=8) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  [VIEWS] Stats indisponibles: {e}")
        return []


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

    # Stats de vues Supabase — boostent la selection (best-effort)
    week_start_date = (today - timedelta(days=LOOKBACK_DAYS)).date()
    view_stats: dict = {}
    try:
        vs = get_view_stats_week(week_start_date.isoformat(), today.date().isoformat())
        view_stats = {d["article_id"]: d["view_count"] for d in vs}
        if view_stats:
            print(f"  [VIEWS] Stats disponibles : {len(view_stats)} articles")
    except Exception:
        pass

    # Scoring : differenciants en premier, boostes par les stats de vues
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
        views = view_stats.get(a.get("id", ""), 0)
        return base + recency + min(views * 5, 30)

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
    date_range = format_date_range_fr(week_start, week_end)
    newsletter_title = f"Pharm'Actus - Actus du {date_range}"

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
            "full_text": a.get("full_text", "")[:4000],
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

    prompt = f"""Tu es Stephen ROBERT, pharmacien consultant, redacteur en chef de Pharm'Actus, influenceur LinkedIn (24K+ abonnes, ~6200 abonnes a la newsletter LinkedIn Pharm'Actus).

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

=== REGLE FINANCES OFFICINE (CRITIQUE - erreur = perte de credibilite immediate face aux experts) ===

INTERDICTIONS ABSOLUES sur les calculs financiers :

1. JAMAIS appliquer un % de remise/discount sur le CA. Les remises labos s'appliquent sur les ACHATS (prix d'achat HT), pas sur le chiffre d'affaires.
   - CA moyen officine 1,2M euros -> Achats HT environ 840K euros (70% du CA)
   - Remise de 4% sur ACHATS = 33 600 euros. PAS 48 000 euros sur le CA.
   - Cette erreur de primaire a deja coute la credibilite de Stephen face a un expert.

2. JAMAIS inventer une fourchette chiffree precise si elle n'est pas dans le texte source fourni.
   - Si la source dit "economies significatives" -> ecrire "economies significatives". Point.
   - Si la source cite un chiffre -> le reproduire exactement tel quel, avec la source.
   - Pas de calcul, pas d'interpolation, pas d'extrapolation.

3. JAMAIS attribuer un chiffre a un organisme (ex: "selon les etudes FCA") sans que ce chiffre soit dans l'article source fourni avec une reference precise.

Reperes financiers officine pour ne pas se planter :
- Marge brute officine moyenne : 27-28% du CA (source Extencia 2025)
- EBE moyen : 10% du CA
- Achats nets : environ 70-72% du CA
- Honoraires dispensation : environ 8-9% du CA

=== ARTICLES DE LA SEMAINE ===
{actus_text}

{lsv_text}

=== CONTEXTE ===
- Numero : Semaine S{week_num} ({week_start.strftime('%d')}-{week_end.strftime('%d %B %Y')})
- A publier le : {monday_next.strftime('%A %d %B %Y')} matin
- Deja ~6200 abonnes a la newsletter LinkedIn

=== STRUCTURE A GENERER ===

Retourne le markdown complet ci-dessous. Le format est aere, SANS separateurs ━ entre les blocs.

```markdown
# Newsletter LinkedIn "Pharm'Actus" — Semaine S{week_num}

**À publier lundi matin (créneau 7h30-8h30 Paris)**

> Image de couverture : `00_cover.png` (en piece jointe)

---

## TITRE LinkedIn (titre EXACT ci-dessous, ne pas modifier)

```
{newsletter_title}
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

[VERSION CONDENSEE LinkedIn : 3 a 4 paragraphes COURTS, 600 a 900 caracteres max. Garde le fait principal + 1 a 2 chiffres cles marquants + 1 ligne actionnable "Demain au comptoir : ...". NE reproduis PAS le full_text en entier : tu resumes pour un format LinkedIn scannable au mobile. Paragraphes separes par UNE ligne vide.]

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

[VERSION CONDENSEE : 4 a 5 paragraphes courts, 500 a 700 caracteres. Garde l'accroche + la chute de l'histoire, coupe les details secondaires. Mots cles en Unicode bold pour rythmer.]

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
2. Pour chaque actu, CONDENSE en version LinkedIn : 3-4 paragraphes courts (600-900 caracteres max), fait principal + 1-2 chiffres cles + 1 ligne "Demain au comptoir". NE reproduis PAS le full_text integralement (trop long pour LinkedIn). Reproduis les chiffres EXACTEMENT, n'en invente aucun.
3. Les TITRES d'actus en UNICODE BOLD (𝟭., 𝟮., etc. + lettres bold). Les caracteres accentues (é, è, à, ç) restent en texte normal.
4. Les LIENS sont les VRAIES URLs fournies, pas inventees.
5. Format AERE : pas de ━━━━ entre les blocs. Juste des sauts de ligne.
6. Pas d'emoji 📰 🔗 devant les liens : juste "Lire sur Pharm'Actus :" et "Source :".
7. L.5122 : ZERO merch sur Rx.
8. Le bloc 1 (intro) DOIT inclure litteralement la phrase :
   "Cette newsletter reprend les actus principales de la semaine derniere. Pour garder un oeil sur ce type d'actus tous les jours, abonnez-vous sur https://actus.pharmalpha.fr/. Bonne lecture !"

Retourne UNIQUEMENT le markdown complet, rien d'autre."""

    # max_tokens=8000 tronquait la newsletter (6 articles full_text + LSV en
    # Unicode bold depassent 8K tokens -> coupure a mi-chemin, bloc 8 jamais
    # genere). Sonnet 4.6 supporte 64K en sortie ; on passe a 32K en streaming
    # (streaming obligatoire >16K pour eviter le timeout SDK).
    response = claude_create(
        client,
        stream=True,
        model="claude-sonnet-4-6",
        max_tokens=32000,
        messages=[{"role": "user", "content": prompt}],
    )

    if getattr(response, "stop_reason", None) == "max_tokens":
        print("  [WARN] stop_reason=max_tokens : la newsletter est TRONQUEE, augmente max_tokens !")

    text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    raw = ("\n".join(text_blocks)).strip() if text_blocks else response.content[0].text.strip()
    return _strip_emdash(raw)


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

    n_autres = max(0, len(actus) - 3)
    prompt = f"""Tu es Stephen ROBERT, pharmacien consultant + influenceur LinkedIn (24K abonnes, ~6200 abonnes newsletter Pharm'Actus).

Tu rediges le POST LinkedIn FEED court qui ANNONCE la newsletter Pharm'Actus (PAS la newsletter elle-meme). Il est publie juste apres la newsletter pour driver trafic + abonnements.

=== STYLE STEPHEN (post feed) ===
- Tutoiement, direct, percutant.
- AUCUN tiret cadratin (—) ni demi-cadratin. AUCUN hashtag dans le corps (ils iront en 1er commentaire).
- Chiffres EXACTS issus des actus fournies, jamais inventes (respecte la regle finances officine : remises sur ACHATS pas sur CA, pas d'extrapolation).
- Pas d'Unicode bold ici : texte normal, ce sont les emojis chiffres 1️⃣2️⃣3️⃣ qui structurent.

=== STRUCTURE EXACTE A REPRODUIRE (garde les sauts de ligne A L'IDENTIQUE) ===
[Hook d'ouverture, 1 ligne courte et punchy, VARIE chaque semaine selon l'actu - ex de ton : "Cette semaine, l'actu ne fait pas dans la dentelle."]
Voilà ce que tu ne peux pas rater :

1️⃣ [Actu 1 : le fait + UN chiffre precis. Une 2e phrase d'impact. Un angle officine/business concret.]

2️⃣ [Actu 2 : meme format, 2 a 3 phrases.]

3️⃣ [Actu 3 : meme format, 2 a 3 phrases.]

… et {n_autres} autres actus + l'anecdote de la semaine.

Tout est dans la newsletter Pharm'Actus que je viens de publier juste en-dessous 👇🏻
Pas encore abonné ?
C'est gratuit, c'est chaque semaine, et ça prend 5 min chrono.

=== ARTICLES TOP 3 DE LA SEMAINE (a teaser dans cet ordre) ===
{top3_text}

=== REGLE LEGALE L.5122 ===
Pas de merch/promo sur Rx (GLP-1, antibiotiques, etc.) : angles macro / reglementaire / formation uniquement.

Genere le post complet, pret a coller sur LinkedIn, en respectant EXACTEMENT la structure et les sauts de ligne ci-dessus. Les 3 dernieres lignes (Tout est dans la newsletter... / Pas encore abonné ? / C'est gratuit...) doivent etre reproduites MOT POUR MOT. Retourne UNIQUEMENT le texte du post, rien d'autre."""

    response = claude_create(
        client,
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    return _strip_emdash(response.content[0].text.strip())


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
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

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
        "subject": f"📰 Pharm'Actus - Actus du {format_date_range_fr(week_start, week_end)} - Brouillon lundi",
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
    """Generate a 1200x675 LinkedIn newsletter cover (S17/18 design)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io

        # Use the dedicated square logo (with globe + PHARM'ACTUS pre-composed)
        logo_path = ROOT_DIR / "assets" / "logo_pharmactus_square.png"
        if not logo_path.exists():
            print(f"  [COVER-ERR] {logo_path} introuvable")
            return None

        W, H = 1200, 675
        BG = "#F5F1EA"
        ORANGE = "#F97316"
        DARK = "#1A1A1A"
        GREY = "#555555"
        FOOTER_H = 60

        # Compute CURRENT ISO week (lundi-dimanche) = semaine recapee, publiee le lundi suivant.
        # La newsletter est generee le vendredi pour publication le lundi : on libelle donc
        # la cover avec la semaine EN COURS (ex W21), coherente avec le sujet de l'email.
        today = datetime.now(PARIS_TZ)
        this_monday = today - timedelta(days=today.weekday())
        this_sunday = this_monday + timedelta(days=6)
        week_num = this_monday.isocalendar()[1]

        months_fr = ["", "JANVIER", "FÉVRIER", "MARS", "AVRIL", "MAI", "JUIN", "JUILLET", "AOÛT", "SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DÉCEMBRE"]
        # ALWAYS full month names (no truncation)
        if this_monday.month == this_sunday.month:
            date_str = f"{this_monday.day} - {this_sunday.day} {months_fr[this_sunday.month]} {this_sunday.year}"
        else:
            date_str = f"{this_monday.day} {months_fr[this_monday.month]} - {this_sunday.day} {months_fr[this_sunday.month]} {this_sunday.year}"

        bg = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(bg)
        draw.rectangle([(0, 0), (8, H - FOOTER_H)], fill=ORANGE)
        draw.rectangle([(0, H - FOOTER_H), (W, H)], fill=DARK)

        def get_font(size, bold=False):
            paths = [
                "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            ]
            for p in paths:
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
            return ImageFont.load_default()

        font_label = get_font(22, bold=True)
        font_huge = get_font(96, bold=True)
        font_dates = get_font(26, bold=True)
        font_sub = get_font(20, bold=False)
        font_footer = get_font(15, bold=True)

        # Logo direct (square format with globe + PHARM'ACTUS pre-composed)
        logo = Image.open(logo_path).convert("RGBA")
        # White -> transparent for clean background
        pixels = logo.load()
        for y in range(logo.size[1]):
            for x in range(logo.size[0]):
                r, g, b, a = pixels[x, y]
                if r > 240 and g > 240 and b > 240:
                    pixels[x, y] = (r, g, b, 0)
        LOGO_W = 380
        ratio = LOGO_W / logo.size[0]
        LOGO_H = int(logo.size[1] * ratio)
        logo = logo.resize((LOGO_W, LOGO_H), Image.LANCZOS)
        logo_x = 60
        logo_y = (H - FOOTER_H - LOGO_H) // 2
        bg.paste(logo, (logo_x, logo_y), logo)

        # Right column
        right_x = 510
        right_top = 110

        label = "LA NEWSLETTER"
        draw.text((right_x, right_top), label, font=font_label, fill=GREY)
        bbox_l = draw.textbbox((0, 0), label, font=font_label)
        label_w, label_h = bbox_l[2] - bbox_l[0], bbox_l[3] - bbox_l[1]
        # Trait orange COURT (45% de la largeur du texte)
        trait_w = int(label_w * 0.45)
        draw.rectangle([(right_x, right_top + label_h + 10), (right_x + trait_w, right_top + label_h + 14)], fill=ORANGE)

        # SEMAINE XX with INCREASED spacing
        semaine_y = right_top + label_h + 50
        draw.text((right_x, semaine_y), f"SEMAINE {week_num}", font=font_huge, fill=DARK)
        bbox_s = draw.textbbox((0, 0), f"SEMAINE {week_num}", font=font_huge)
        semaine_h = bbox_s[3] - bbox_s[1]

        # Dates : ESPACEMENT augmente (45 au lieu de 15)
        dates_y = semaine_y + semaine_h + 45
        draw.text((right_x, dates_y), date_str, font=font_dates, fill=ORANGE)
        bbox_d = draw.textbbox((0, 0), date_str, font=font_dates)
        dates_h = bbox_d[3] - bbox_d[1]

        tagline_y = dates_y + dates_h + 30
        draw.text((right_x, tagline_y), "5 actus pharma + 1 saviez-vous.", font=font_sub, fill=GREY)
        draw.text((right_x, tagline_y + 30), "Je vous résume l'actus de la semaine en 5min chrono.", font=font_sub, fill=GREY)

        # Footer
        footer_y = H - FOOTER_H + 22
        draw.text((40, footer_y), "STEPHEN ROBERT  |  PHARM'ALPHA", font=font_footer, fill="#FFFFFF")
        url = "pharmalpha.fr/actus"
        bbox_url = draw.textbbox((0, 0), url, font=font_footer)
        draw.text((W - 40 - (bbox_url[2] - bbox_url[0]), footer_y), url, font=font_footer, fill=ORANGE)

        buf = io.BytesIO()
        bg.save(buf, "PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"  [COVER-ERR] {e}")
        return None



BREVO_LIST_HEBDO = 8  # Abonnes frequence hebdomadaire


def send_to_hebdo_list(html_content: str, week_label: str) -> None:
    """Envoie le digest hebdo a tous les abonnes de la liste Hebdo (id 8)."""
    api_key = os.environ.get("BREVO_API_KEY", "")
    if not api_key:
        print("  [HEBDO] BREVO_API_KEY non definie, envoi liste 8 skipped")
        return

    # Recuperer les contacts de la liste 8
    all_contacts = []
    offset = 0
    limit = 50
    headers = {"api-key": api_key, "Accept": "application/json"}
    while True:
        url = f"{BREVO_API_BASE}/contacts/lists/{BREVO_LIST_HEBDO}/contacts?limit={limit}&offset={offset}"
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
            print(f"  [HEBDO-ERR] Impossible de recuperer la liste 8: {e}")
            return

    emails = [c["email"] for c in all_contacts if c.get("email")]
    if not emails:
        print("  [HEBDO] Aucun abonne dans la liste Hebdo (id 8)")
        return

    print(f"  [HEBDO] {len(emails)} abonne(s) dans la liste Hebdo")
    subject = f"Pharm'Actus - Resume de la semaine ({week_label})"
    send_url = f"{BREVO_API_BASE}/smtp/email"
    sent = 0
    for email in emails:
        payload = json.dumps({
            "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
            "replyTo": {"email": EMAIL_RECIPIENT, "name": SENDER_NAME},
            "to": [{"email": email}],
            "subject": subject,
            "htmlContent": html_content,
        }).encode("utf-8")
        try:
            req = urllib.request.Request(
                send_url, data=payload,
                headers={"api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                json.loads(resp.read())
            sent += 1
        except Exception as e:
            print(f"  [HEBDO-ERR] {email}: {e}")
    print(f"  [HEBDO] {sent}/{len(emails)} emails envoyes")

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
