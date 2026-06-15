"""
daily_trends.py — Radar pharmacien : decouverte dynamique via pytrends rising

Principe : on ne cherche PAS une liste fixe de marques ou pathologies.
On interroge pytrends.related_queries(type="rising") sur des seeds larges
couvrant l'univers pharma/para. Google Trends remonte automatiquement
ce qui monte le plus fort cette semaine en France.

Resultat : chaque semaine peut faire emerger des termes totalement nouveaux
(marque inconnue, ingredient viral, symptome saisonnier) sans aucune
intervention manuelle.

Seeds patho  → besoins / symptomes / requetes sante patients
Seeds marque → produits / marques / ingredients tendance para

Output : output/trends_daily.json
Cadence : quotidienne (lance avant update_actus.py dans daily-update.yml)
"""

import time
import json
import os
import sys
import datetime
import re

# Force UTF-8 sur Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from pytrends.request import TrendReq
    from pytrends.exceptions import TooManyRequestsError
except ImportError:
    print("[ERREUR] pytrends non installe. Lance : pip install pytrends 'urllib3<2'")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────
TOP_N          = 5     # lignes dans le tableau
SLEEP_BEFORE_BATCH1 = 20   # pause avant le 1er batch (evite 429 immediate)
SLEEP_BATCHES  = 68    # secondes entre les 2 appels pytrends (evite 429)
SLEEP_RETRY    = 130   # pause si premier 429
MAX_RETRIES    = 3     # augmente de 2 à 3 pour robustesse
# today 1-m = 30 jours glissants, granularite quotidienne.
# Beaucoup plus de points de donnees que "now 7-d" → related_queries fonctionnel.
# "Rising" = requetes dont la croissance est la plus forte sur ce mois.
TIMEFRAME      = "today 1-m"
GEO            = "FR"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "trends_daily.json")

# ── Seeds ─────────────────────────────────────────────────────────────
# Seeds BESOINS / PATHOLOGIES
# Termes a fort volume de recherche en France (>10K/mois estimés).
# Volume eleve = Google Trends peut calculer des related_queries "rising".
# Seeds trop niche → DataFrames vides (experience du 2026-05-29).
SEEDS_PATHO = [
    "pharmacie",              # seed #1 : fort volume, univers large
    "vitamine",               # complementation, tres cherche
    "allergie",               # saisonnier, fort volume printemps-ete
    "fatigue",                # concern sante permanent
    "peau soin",              # dermatologie / cosmetique
]

# Seeds SOINS / BIEN-ETRE (2e colonne du radar)
# Focus sur les categories OTC / complements / bien-etre.
# Seeds differents de SEEDS_PATHO pour diversifier les resultats.
SEEDS_SOIN = [
    "sommeil",               # insomnie, troubles du sommeil
    "stress anxiete",        # bien-etre mental
    "digestion",             # gastro, ballonnements
    "douleur",               # antidouleur, anti-inflammatoire OTC
    "immunite",              # defenses immunitaires
]

# ── Filtrage bruit ────────────────────────────────────────────────────
# Blocklist : sujets clairement hors-sujet pharma
_BLOCKLIST_RE = re.compile(
    r"\b(prix|acheter|achat|promo|solde|pas cher|gratuit|livraison|"
    r"recette|cuisine|restaurant|sport|foot|musique|film|serie|"
    r"politique|election|immobilier|voiture|bourse|crypto|"
    r"meteo|voyag|hotel|airbnb|amazon|aliexpress)\b",
    re.I | re.UNICODE,
)

# Mots parasites issus des seeds (pas utiles dans l'affichage)
_STRIP_WORDS = [
    " pharmacie", " avis", " tendance", " france", " naturel",
    " 2025", " 2026", " 2024", " traitement", " soin",
]


def _is_noise(query: str) -> bool:
    return bool(_BLOCKLIST_RE.search(query))


def _clean_display(query: str) -> str:
    """Nettoie le terme pour l'affichage : retire les mots de contexte, capitalise."""
    q = query.lower()
    for word in _STRIP_WORDS:
        q = q.replace(word, "")
    q = " ".join(q.split())          # normalise espaces
    q = q.strip().capitalize()
    return q[:40] if q else query[:40]


def _format_value(val) -> tuple:
    """Retourne (delta_label, trend) depuis la valeur pytrends.

    Affiche l'indice brut pytrends (intensite de la hausse) avec une fleche :
      - Breakout → 🔥 Nouveau (terme en explosion, hors echelle)
      - Entier    → ↑ {valeur} (ex: ↑ 3 420 — plus c'est haut, plus ca monte fort)
    Note : l'indice n'est PAS un nb de recherches absolu, c'est un score de
    croissance relative Google Trends (plus eleve = hausse plus intense).
    """
    s = str(val)
    if s == "Breakout":
        return ("🔥 Nouveau", "up")
    try:
        n = int(s)
        # Formatage avec espace comme separateur de milliers (lisibilite FR)
        formatted = f"{n:,}".replace(",", " ")  # espace fine insecable
        return (f"↑ {formatted}", "up")
    except (ValueError, TypeError):
        return ("↑ Hausse", "up")


# ── Decouverte rising ─────────────────────────────────────────────────

def _extract_items(related: dict, seeds: list, query_type: str) -> list:
    """Extrait et deduplique les items rising/top depuis le dict related_queries."""
    seen: set  = set()
    items: list = []

    for seed in seeds[:5]:
        seed_result = related.get(seed)
        if not seed_result:
            print(f"    [DEBUG] seed '{seed}' → pas de resultat")
            continue
        df = seed_result.get(query_type)
        if df is None or (hasattr(df, "empty") and df.empty):
            print(f"    [DEBUG] seed '{seed}' type='{query_type}' → DataFrame vide")
            continue

        print(f"    [DEBUG] seed '{seed}' type='{query_type}' → {len(df)} lignes")
        for _, row in df.iterrows():
            raw_query = str(row.get("query", "")).strip()
            val       = row.get("value", 0)

            if not raw_query or len(raw_query) < 3:
                continue
            if _is_noise(raw_query):
                continue

            key = raw_query.lower()
            if key in seen:
                continue
            seen.add(key)

            sort_val = 99999 if str(val) == "Breakout" else (
                int(val) if str(val).isdigit() else 0
            )
            delta_label, trend = _format_value(val)

            items.append({
                "display":     _clean_display(raw_query),
                "delta_label": delta_label,
                "trend":       trend,
                "_sort":       sort_val,
            })

    items.sort(key=lambda x: -x["_sort"])
    for item in items:
        del item["_sort"]
    return items[:TOP_N]


def discover_rising(seeds: list, pt: TrendReq, label: str) -> list:
    """
    Lance build_payload + related_queries sur les seeds fournis.
    Essaie d'abord type='rising'. Si vide, fallback sur type='top'.
    Retourne une liste de dicts [{display, delta_label, trend}].
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pt.build_payload(seeds[:5], timeframe=TIMEFRAME, geo=GEO)
            time.sleep(2)
            related = pt.related_queries()
            break
        except TooManyRequestsError:
            if attempt < MAX_RETRIES:
                print(f"  [429] Tentative {attempt}/{MAX_RETRIES} — pause {SLEEP_RETRY}s...")
                time.sleep(SLEEP_RETRY)
            else:
                print(f"  [429] Echec apres {MAX_RETRIES} tentatives pour {label}")
                return []
        except Exception as e:
            print(f"  [ERR] {label} : {e}")
            return []

    # Essai 1 : rising (termes en forte hausse → le plus interessant)
    items = _extract_items(related, seeds, "rising")

    if not items:
        # Essai 2 : top (requetes les plus populaires liees aux seeds)
        # Moins dynamique mais garantit un resultat
        print(f"  [INFO] rising vide pour {label} → fallback sur 'top'")
        items = _extract_items(related, seeds, "top")

    return items


# ── Main ─────────────────────────────────────────────────────────────

def main():
    today    = datetime.date.today()
    start    = today - datetime.timedelta(days=6)
    MOIS     = ["", "jan.", "fev.", "mars", "avr.", "mai", "juin",
                "juil.", "aout", "sept.", "oct.", "nov.", "dec."]
    window_label = (
        f"{start.day} {MOIS[start.month]} "
        f"— {today.day} {MOIS[today.month]} {today.year}"
    )

    print(f"Radar pharmacien (pytrends rising) — {today.isoformat()}")
    print(f"Fenetre : {window_label} | Geo : {GEO}")
    print("-" * 60)

    pt = TrendReq(hl="fr-FR", tz=60)

    # ── Pause initiale (evite 429 immediate au demarrage CI) ──────────
    print(f"Pause initiale {SLEEP_BEFORE_BATCH1}s (anti rate-limit)...")
    time.sleep(SLEEP_BEFORE_BATCH1)

    # ── Batch 1 : besoins / pathologies ──────────────────────────────
    print(f"[1/2] Seeds besoins patients ({len(SEEDS_PATHO)} seeds)...")
    patho_top = discover_rising(SEEDS_PATHO, pt, "patho")
    print(f"  -> {len(patho_top)} termes remontes")
    for p in patho_top:
        print(f"     {p['display']:38s} {p['delta_label']}")

    # ── Pause inter-batch ─────────────────────────────────────────────
    if patho_top is not None:   # toujours vrai, mais evite exit precoce
        print(f"\nPause {SLEEP_BATCHES}s (rate limit pytrends)...")
        time.sleep(SLEEP_BATCHES)

    # ── Batch 2 : soins / bien-etre ──────────────────────────────────
    print(f"\n[2/2] Seeds soins/bien-etre ({len(SEEDS_SOIN)} seeds)...")
    soin_top = discover_rising(SEEDS_SOIN, pt, "soin")
    print(f"  -> {len(soin_top)} termes remontes")
    for s in soin_top:
        print(f"     {s['display']:38s} {s['delta_label']}")

    # ── Fallback colonne vide : reutilise les donnees du jour precedent ──
    # Evite colonnes vides si pytrends rate-limite un des deux batchs
    prev_data = {}
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                prev_data = json.load(f)
        except Exception:
            pass

    if not patho_top and prev_data.get("pathologies"):
        patho_top = prev_data["pathologies"]
        print(f"  [FALLBACK] pathologies vide -> reutilise donnees precedentes ({len(patho_top)} termes)")

    if not soin_top and prev_data.get("soins"):
        soin_top = prev_data["soins"]
        print(f"  [FALLBACK] soins vide -> reutilise donnees precedentes ({len(soin_top)} termes)")

    # ── Sauvegarde ────────────────────────────────────────────────────
    output = {
        "generated_at": today.isoformat(),
        "window_label": window_label,
        "has_history":  True,   # pytrends rising = deja relatif, pas besoin d'historique
        "delta_source": "pytrends_rising",
        "pathologies":  patho_top,
        "soins":        soin_top,
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nOK -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
