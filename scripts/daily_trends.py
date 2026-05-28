"""
daily_trends.py — Radar pharmacien quotidien (fenetre 7 jours glissants)
Source  : Google News RSS, nb articles sur when:7d
Cadence : quotidienne (lance par daily-update.yml avant update_actus.py)
Output  : output/trends_daily.json
          output/trends_daily_history.json (historique 14 jours)

Logique delta S-1 :
  - Aujourd'hui   = count RSS du jour  (articles 7 derniers jours)
  - Semaine prec. = count RSS enregistre il y a 7 jours
  - Delta         = (auj - S-7) / max(1, S-7) * 100 (arrondi entier)
"""

import feedparser
import urllib.parse
import time
import datetime
import json
import os
import sys

# Force UTF-8 sur Windows (evite UnicodeEncodeError cp1252)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Config ────────────────────────────────────────────────────────────
SLEEP_BETWEEN = 0.5    # secondes entre requetes RSS (evite 429)
TOP_N         = 5      # lignes dans le tableau
HISTORY_DAYS  = 16     # jours d'historique conserves (>14 pour securite)

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT    = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR   = os.path.join(REPO_ROOT, "output")
HISTORY_FILE = os.path.join(OUTPUT_DIR, "trends_daily_history.json")
OUTPUT_FILE  = os.path.join(OUTPUT_DIR, "trends_daily.json")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ── Catalogues ────────────────────────────────────────────────────────
# (query_google_news, affichage)
PATHOLOGIES = [
    ("brulure coup de soleil",             "Brulure / Coup de soleil"),
    ("piqure moustique insecte",           "Piqures moustiques"),
    ("allergie cutanee peau",              "Allergie cutanee"),
    ("rhinite allergique pollen",          "Rhinite / Pollen"),
    ("insomnie sommeil pharmacie",         "Insomnie"),
    ("mycose pied ongle pharmacie",        "Mycose pied"),
    ("diarrhee gastro voyageur",           "Diarrhee / Gastro"),
    ("reflux gastrique brulure estomac",   "Reflux gastrique"),
    ("constipation transit pharmacie",     "Constipation"),
    ("toux seche irritante pharmacie",     "Toux seche"),
    ("sinusite rhume pharmacie",           "Sinusite / Rhume"),
    ("douleur articulaire musculaire",     "Douleur articulaire"),
    ("carence vitamine D soleil",          "Vitamine D"),
    ("magnesium stress fatigue",           "Magnesium / Stress"),
    ("deshydratation chaleur canicule",    "Deshydratation chaleur"),
]

MARQUES = [
    ("SVR pharmacie",                      "SVR"),
    ("Hydratis hydratation",               "Hydratis"),
    ("Topicrem soin pharmacie",            "Topicrem"),
    ("Avene soin pharmacie",               "Avene"),
    ("Bioderma soin pharmacie",            "Bioderma"),
    ("La Roche-Posay pharmacie",           "La Roche-Posay"),
    ("CeraVe pharmacie",                   "CeraVe"),
    ("Uriage pharmacie",                   "Uriage"),
    ("Ducray pharmacie",                   "Ducray"),
    ("Pileje complement alimentaire",      "Pileje"),
    ("Mium Lab complement",                "Mium Lab"),
    ("Novoma complement alimentaire",      "Novoma"),
    ("Caudalie pharmacie",                 "Caudalie"),
    ("Nuxe pharmacie",                     "Nuxe"),
    ("Bonjour Drink",                      "Bonjour Drink"),
]


# ── Helpers ───────────────────────────────────────────────────────────

def build_url(query: str, period: str = "7d") -> str:
    full_query = f"{query} when:{period}"
    encoded = urllib.parse.quote(full_query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=fr&gl=FR&ceid=FR:fr"


def fetch_count(url: str) -> int:
    """Retourne le nb d'articles dans le feed RSS. 0 si erreur."""
    try:
        feed = feedparser.parse(url, agent=UA, request_headers={"User-Agent": UA})
        if feed.bozo and not feed.entries:
            return 0
        return len(feed.entries)
    except Exception:
        return 0


def fetch_two_windows(query: str) -> tuple:
    """Retourne (count_7d, count_prev_week).

    count_prev_week = count_14d - count_7d
    = estimation des articles publiés entre j-14 et j-7 (semaine precedente).
    Permet un delta S-1 immediat des le 1er run, sans historique.
    Limite : approximatif si RSS depasse 100 (cap Google News) — acceptable
    pour des requetes specifiques (marques / pathologies + pharmacie).
    """
    count_7d  = fetch_count(build_url(query, "7d"))
    time.sleep(SLEEP_BETWEEN)
    count_14d = fetch_count(build_url(query, "14d"))
    count_prev = max(0, count_14d - count_7d)
    return count_7d, count_prev


def load_history() -> dict:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_history(history: dict) -> None:
    """Garde les HISTORY_DAYS derniers jours uniquement."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=HISTORY_DAYS)).isoformat()
    pruned = {k: v for k, v in history.items() if k >= cutoff}
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(pruned, f, ensure_ascii=False, indent=2)


def compute_delta(current: int, previous) -> tuple:
    """Retourne (delta_pct: int|None, label: str, trend: str)."""
    if previous is None:
        return None, "—", "neutral"
    if previous == 0 and current == 0:
        return 0, "0%", "neutral"
    pct = round((current - previous) / max(1, previous) * 100)
    sign = "+" if pct >= 0 else ""
    label = f"{sign}{pct}%"
    trend = "up" if pct > 5 else ("down" if pct < -5 else "neutral")
    return pct, label, trend


def build_items(catalogue, today_data: dict, prev_data: dict,
                live_prev_data: dict = None) -> list:
    """Construit la liste d'items triée par delta desc, puis count desc.

    Priorite pour 'previous' :
      1. prev_data  (historique stocke J-7) — le plus fiable
      2. live_prev_data (proxy 14d-7d)      — disponible des le 1er run
      3. None                               — pas de comparaison possible
    """
    items = []
    for query, display in catalogue:
        count = today_data.get(query, 0)
        previous = (
            prev_data.get(query)      if prev_data
            else live_prev_data.get(query) if live_prev_data
            else None
        )
        pct, label, trend = compute_delta(count, previous)
        items.append({
            "query":       query,
            "display":     display,
            "count":       count,
            "delta_pct":   pct,
            "delta_label": label,
            "trend":       trend,
        })

    # Tri : delta desc (None en bas), puis count desc
    def sort_key(x):
        d = x["delta_pct"]
        return (-(d if d is not None else -9999), -x["count"])

    items.sort(key=sort_key)
    return items[:TOP_N]


# ── Main ─────────────────────────────────────────────────────────────

def main():
    today     = datetime.date.today()
    today_key = today.isoformat()
    prev_key  = (today - datetime.timedelta(days=7)).isoformat()

    history   = load_history()
    prev_data = history.get(prev_key, {})
    has_prev  = bool(prev_data)

    all_queries = PATHOLOGIES + MARQUES
    total = len(all_queries)
    # 2 fenetres par requete (7d + 14d) sauf si historique deja dispo
    nb_req = total * (1 if has_prev else 2)
    print(f"Radar pharmacien — {today_key} ({nb_req} requetes, "
          f"source S-1 : {'historique' if has_prev else 'proxy 14d-7d'})")

    today_data: dict     = {}   # count 7d (pour historique)
    live_prev_data: dict = {}   # count prev week via 14d-7d (fallback 1er run)

    for i, (query, display) in enumerate(all_queries, start=1):
        if has_prev:
            # Historique dispo → 1 seule requete (7d)
            count = fetch_count(build_url(query, "7d"))
            time.sleep(SLEEP_BETWEEN)
            today_data[query]     = count
            print(f"  [{i:2}/{total}] {display:35s} : {count}")
        else:
            # Pas d'historique → 2 requetes (7d + 14d)
            count_7d, count_prev = fetch_two_windows(query)
            today_data[query]     = count_7d
            live_prev_data[query] = count_prev
            print(f"  [{i:2}/{total}] {display:35s} : {count_7d} (prev≈{count_prev})")

    # Sauvegarde historique (uniquement count_7d)
    history[today_key] = today_data
    save_history(history)

    # Construction tops
    # has_prev=True  → prev_data depuis historique, live_prev_data ignoré
    # has_prev=False → prev_data vide, live_prev_data = proxy 14d-7d
    patho_top  = build_items(PATHOLOGIES, today_data, prev_data,
                             live_prev_data if not has_prev else None)
    marque_top = build_items(MARQUES,     today_data, prev_data,
                             live_prev_data if not has_prev else None)

    # Plage de dates lisible (ex : "22 mai — 28 mai 2026")
    start = today - datetime.timedelta(days=6)
    MOIS  = ["", "jan.", "fev.", "mars", "avr.", "mai", "juin",
             "juil.", "aout", "sept.", "oct.", "nov.", "dec."]
    window_label = (
        f"{start.day} {MOIS[start.month]} "
        f"— {today.day} {MOIS[today.month]} {today.year}"
    )

    output = {
        "generated_at":   today_key,
        "window_label":   window_label,
        "has_history":    has_prev,
        "delta_source":   "historique" if has_prev else "proxy_14d_minus_7d",
        "pathologies":    patho_top,
        "marques":        marque_top,
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nOK -> {OUTPUT_FILE}")
    print(f"  Source S-1 : {'historique (precise)' if has_prev else 'proxy 14d-7d (approx — passe en historique a J+7)'}")


if __name__ == "__main__":
    main()
