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
SLEEP_BATCHES  = 68    # secondes entre les 2 appels pytrends (evite 429)
SLEEP_RETRY    = 130   # pause si premier 429
MAX_RETRIES    = 2
TIMEFRAME      = "now 7-d"  # fenetre Google Trends
GEO            = "FR"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "trends_daily.json")

# ── Seeds ─────────────────────────────────────────────────────────────
# Seeds BESOINS / PATHOLOGIES
# -> ce que les patients cherchent avant d'aller en pharmacie
SEEDS_PATHO = [
    "symptome traitement naturel",
    "soin peau pharmacie",
    "allergie infection traitement",
    "fatigue carence vitamine",
    "douleur remede pharmacie",
]

# Seeds PRODUITS / MARQUES para
# -> produits, marques, ingredients tendance dans l'univers pharma/para
SEEDS_MARQUE = [
    "complement alimentaire pharmacie avis",
    "cosmetique pharmacie tendance",
    "parapharmacie produit soin",
    "serum creme pharmacie",
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
    """Retourne (delta_label, trend) depuis la valeur pytrends."""
    s = str(val)
    if s == "Breakout":
        return ("Nouveau !", "up")
    try:
        n = int(s)
        return (f"+{n}%", "up")
    except (ValueError, TypeError):
        return (s, "up")


# ── Decouverte rising ─────────────────────────────────────────────────

def discover_rising(seeds: list, pt: TrendReq, label: str) -> list:
    """
    Lance build_payload + related_queries("rising") sur les seeds fournis.
    Retourne une liste de dicts [{display, delta_label, trend, _sort}]
    triee par valeur descending, depourvue des doublons et du bruit.
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

    seen: set = set()
    items: list = []

    for seed in seeds[:5]:
        seed_result = related.get(seed)
        if not seed_result:
            continue
        df = seed_result.get("rising")
        if df is None or (hasattr(df, "empty") and df.empty):
            continue

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

            # Sort key : Breakout = 99999, sinon valeur numerique
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

    # Tri par valeur descending
    items.sort(key=lambda x: -x["_sort"])
    # Nettoyage cle interne
    for item in items:
        del item["_sort"]

    return items[:TOP_N]


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

    # ── Batch 2 : produits / marques ─────────────────────────────────
    print(f"\n[2/2] Seeds produits/marques ({len(SEEDS_MARQUE)} seeds)...")
    marque_top = discover_rising(SEEDS_MARQUE, pt, "marque")
    print(f"  -> {len(marque_top)} termes remontes")
    for m in marque_top:
        print(f"     {m['display']:38s} {m['delta_label']}")

    # ── Sauvegarde ────────────────────────────────────────────────────
    output = {
        "generated_at": today.isoformat(),
        "window_label": window_label,
        "has_history":  True,   # pytrends rising = deja relatif, pas besoin d'historique
        "delta_source": "pytrends_rising",
        "pathologies":  patho_top,
        "marques":      marque_top,
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nOK -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
