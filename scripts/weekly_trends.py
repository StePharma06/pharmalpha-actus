#!/usr/bin/env python3
"""
Pharm'Actus - Tendances hebdomadaires marques CA + Cosméto
Tourne chaque lundi 6h UTC via GitHub Actions.
Génère output/trends_latest.json + output/trends_YYYY-WXX.json
"""

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from pytrends.request import TrendReq
from pytrends.exceptions import TooManyRequestsError

# ── Constantes ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"

ANCHOR = "Bioderma"        # Inclus dans chaque batch pour normaliser les scores
BATCH_SIZE = 4             # 4 marques + 1 anchor = 5 max pytrends
SLEEP_BETWEEN_BATCHES = 65 # secondes (évite HTTP 429)
RETRY_SLEEP = 120          # secondes en cas de TooManyRequestsError

# ── Catalogue complet (query_google_trends, affichage, categorie) ────────
CATALOGUE = [
    ("Hydratis", "Hydratis", "CA"),
    ("Pileje Lactibiane", "Pileje Lactibiane", "CA"),
    ("Novoma", "Novoma", "CA"),
    ("Granions", "Granions", "CA"),
    ("Oenobiol", "Oenobiol", "CA"),
    ("Forte Pharma", "Forté Pharma", "CA"),
    ("Vitarmonyl", "Vitarmonyl", "CA"),
    ("Juvamine", "Juvamine", "CA"),
    ("Sunday Natural", "Sunday Natural", "CA"),
    ("Mium Lab", "Mium Lab", "CA"),
    ("Dynveo", "Dynveo", "CA"),
    ("Nutergia", "Nutergia", "CA"),
    ("Vitavea", "Vitavea", "CA"),
    ("Ineldea", "Ineldea", "CA"),
    ("Alvityl", "Alvityl", "CA"),
    ("Azinc", "Azinc", "CA"),
    ("Bion3", "Bion3", "CA"),
    ("Supradyn", "Supradyn", "CA"),
    ("Berocca", "Berocca", "CA"),
    ("Biocyte", "Biocyte", "CA"),
    ("Arkopharma", "Arkopharma", "CA"),
    ("Arkorelax", "Arkorelax", "CA"),
    ("Naturactive", "Naturactive", "CA"),
    ("Herbesan", "Herbesan", "CA"),
    ("Santarome", "Santarome", "CA"),
    ("Propolia", "Propolia", "CA"),
    ("Jolly Mama", "Jolly Mama", "CA"),
    ("Synactifs", "Synactifs", "CA"),
    ("D-Stress Synergia", "D-Stress", "CA"),
    ("Physiomance", "Physiomance", "CA"),
    ("Phytea", "Phytea", "CA"),
    ("Solgar", "Solgar", "CA"),
    ("Lehning", "Lehning", "CA"),
    ("Bonjour Drink", "Bonjour Drink", "CA"),
    ("Biocyte Keratin", "Biocyte Keratin", "CA"),
    ("CeraVe", "CeraVe", "Cosméto"),
    ("Bioderma Sensibio", "Bioderma Sensibio", "Cosméto"),
    ("Bioderma Atoderm", "Bioderma Atoderm", "Cosméto"),
    ("Avene Cicalfate", "Avène Cicalfate", "Cosméto"),
    ("La Roche-Posay Cicaplast", "LRP Cicaplast", "Cosméto"),
    ("La Roche-Posay Effaclar", "LRP Effaclar", "Cosméto"),
    ("Nuxe Huile Prodigieuse", "Nuxe Huile Prodigieuse", "Cosméto"),
    ("SVR Cicavit", "SVR Cicavit", "Cosméto"),
    ("SVR Sebiaclear", "SVR Sebiaclear", "Cosméto"),
    ("Eucerin", "Eucerin", "Cosméto"),
    ("Uriage", "Uriage", "Cosméto"),
    ("Vichy Dercos", "Vichy Dercos", "Cosméto"),
    ("Vichy Liftactiv", "Vichy Liftactiv", "Cosméto"),
    ("Ducray", "Ducray", "Cosméto"),
    ("Klorane", "Klorane", "Cosméto"),
    ("Rene Furterer", "René Furterer", "Cosméto"),
    ("Filorga", "Filorga", "Cosméto"),
    ("Caudalie", "Caudalie", "Cosméto"),
    ("Embryolisse", "Embryolisse", "Cosméto"),
    ("Mustela", "Mustela", "Cosméto"),
    ("Nuxe Reve de Miel", "Nuxe Rêve de Miel", "Cosméto"),
    ("Lierac", "Lierac", "Cosméto"),
    ("Institut Esthederm", "Institut Esthederm", "Cosméto"),
    ("A-Derma", "A-Derma", "Cosméto"),
    ("Aderma Exomega", "Aderma Exomega", "Cosméto"),
    ("Topicrem", "Topicrem", "Cosméto"),
    ("Homeoplasmine", "Homeoplasmine", "Cosméto"),
    ("Synactifs Actipur", "Actipur", "Cosméto"),
    ("SkinCeuticals", "SkinCeuticals", "Cosméto"),
    ("Bepanthen", "Bepanthen", "Cosméto"),
    ("Phyto capillaire", "Phyto", "Cosméto"),
    ("Jonzac", "Jonzac", "Cosméto"),
    ("Cattier", "Cattier", "Cosméto"),
    ("Meme Cosmetics", "Même Cosmetics", "Cosméto"),
    ("Melvita", "Melvita", "Cosméto"),
]


# ── Helpers ──────────────────────────────────────────────────────────────

def _current_week_label():
    """Retourne le label ISO semaine courante, ex. '2026-W22'."""
    now = datetime.now(timezone.utc)
    return now.strftime("%G-W%V")


def _week_label_offset(offset_weeks: int) -> str:
    """Retourne le label de la semaine courante + offset_weeks (négatif = passé)."""
    now = datetime.now(timezone.utc)
    shifted = now + timedelta(weeks=offset_weeks)
    return shifted.strftime("%G-W%V")


def _load_week_data(week_label: str) -> dict | None:
    """Charge l'archive JSON d'une semaine passée. Retourne None si absent."""
    path = OUTPUT_DIR / f"trends_{week_label}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _score_for_query(data: dict | None, query: str) -> float | None:
    """Extrait le score d'une marque dans un payload archivé. Retourne None si absent."""
    if not data:
        return None
    for item in data.get("all_ranked", []):
        if item.get("query") == query:
            return item.get("score")
    return None


def _var_pct(current: float, previous: float | None) -> str:
    """Calcule la variation en %. 'N/A' si pas de données précédentes."""
    if previous is None:
        return "N/A"
    if previous == 0:
        return "+∞" if current > 0 else "0%"
    pct = round((current - previous) / previous * 100)
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct}%"


# ── Fetch pytrends ────────────────────────────────────────────────────────

def _fetch_batch(pt: TrendReq, batch: list[tuple]) -> dict[str, float]:
    """
    Fetch un batch de marques avec l'anchor.
    Retourne un dict {query: score_normalisé}.
    Gère TooManyRequestsError avec 1 retry après RETRY_SLEEP secondes.
    """
    queries = [item[0] for item in batch]
    kw_list = [ANCHOR] + queries

    def _do_fetch() -> dict[str, float]:
        pt.build_payload(kw_list, cat=0, timeframe="now 7-d", geo="FR")
        df = pt.interest_over_time()

        scores: dict[str, float] = {}

        if df is None or df.empty:
            # Aucune donnée pour tout le batch
            for q in queries:
                scores[q] = 0.0
            return scores

        anchor_score = float(df[ANCHOR].mean()) if ANCHOR in df.columns else 100.0
        anchor_score = max(anchor_score, 1.0)  # évite division par zéro

        for q in queries:
            if q in df.columns:
                raw = float(df[q].mean())
                scores[q] = round(raw / anchor_score * 100, 2)
            else:
                scores[q] = 0.0

        return scores

    try:
        return _do_fetch()
    except TooManyRequestsError:
        print(f"  [429] Rate-limited. Attente {RETRY_SLEEP}s puis retry...")
        time.sleep(RETRY_SLEEP)
        try:
            return _do_fetch()
        except TooManyRequestsError:
            print("  [429] Retry échoué. Score 0.0 pour ce batch.")
            return {q: 0.0 for q in queries}
    except Exception as e:
        print(f"  [ERR] Batch error: {e}. Score 0.0 pour ce batch.")
        return {q: 0.0 for q in queries}


def fetch_all_scores() -> dict[str, float]:
    """
    Parcourt tous les batches du CATALOGUE et retourne {query: score}.
    Sleep SLEEP_BETWEEN_BATCHES secondes entre chaque batch.
    """
    pt = TrendReq(hl="fr-FR", tz=60, timeout=(10, 30), retries=3, backoff_factor=1.5)
    all_scores: dict[str, float] = {}

    batches = [
        CATALOGUE[i : i + BATCH_SIZE]
        for i in range(0, len(CATALOGUE), BATCH_SIZE)
    ]
    total = len(batches)

    for idx, batch in enumerate(batches, 1):
        queries = [item[0] for item in batch]
        print(f"  [Batch {idx}/{total}] {', '.join(queries)}")
        scores = _fetch_batch(pt, batch)
        all_scores.update(scores)

        if idx < total:
            print(f"  [SLEEP] {SLEEP_BETWEEN_BATCHES}s...")
            time.sleep(SLEEP_BETWEEN_BATCHES)

    return all_scores


# ── Construction payload JSON ─────────────────────────────────────────────

def build_payload(scores: dict[str, float]) -> dict:
    """
    Construit le payload complet avec top20 et all_ranked.
    Charge les archives S-1 (semaine passée) et M-1 (~4 semaines) pour les variations.
    """
    week_label = _current_week_label()
    prev_week_label = _week_label_offset(-1)
    prev_month_label = _week_label_offset(-4)

    prev_week_data = _load_week_data(prev_week_label)
    prev_month_data = _load_week_data(prev_month_label)

    # Assembler toutes les marques avec leur score + variations
    ranked_items = []
    for query, display, category in CATALOGUE:
        score = scores.get(query, 0.0)
        prev_s1 = _score_for_query(prev_week_data, query)
        prev_m1 = _score_for_query(prev_month_data, query)

        ranked_items.append({
            "query": query,
            "display": display,
            "category": category,
            "score": score,
            "var_s1": _var_pct(score, prev_s1),
            "var_m1": _var_pct(score, prev_m1),
        })

    # Tri décroissant par score
    ranked_items.sort(key=lambda x: x["score"], reverse=True)

    # Ajout du rang
    for i, item in enumerate(ranked_items, 1):
        item["rank"] = i

    top20 = ranked_items[:20]

    return {
        "week": week_label,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "top20": top20,
        "all_ranked": ranked_items,
    }


# ── Persistance ──────────────────────────────────────────────────────────

def save_payload(payload: dict) -> None:
    """Sauvegarde trends_latest.json et trends_YYYY-WXX.json."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    week_label = payload["week"]
    archive_path = OUTPUT_DIR / f"trends_{week_label}.json"
    latest_path = OUTPUT_DIR / "trends_latest.json"

    content = json.dumps(payload, ensure_ascii=False, indent=2)

    archive_path.write_text(content, encoding="utf-8")
    latest_path.write_text(content, encoding="utf-8")

    print(f"  [OK] Sauvegardé : {archive_path.name} + trends_latest.json")
    print(f"  [OK] Top 3 : " + " | ".join(
        f"#{item['rank']} {item['display']} ({item['score']})"
        for item in payload["top20"][:3]
    ))


# ── Entrypoint ────────────────────────────────────────────────────────────

def main():
    print(f"[weekly_trends] Démarrage — {_current_week_label()}")
    print(f"  {len(CATALOGUE)} marques, {(len(CATALOGUE) + BATCH_SIZE - 1) // BATCH_SIZE} batches")

    scores = fetch_all_scores()
    payload = build_payload(scores)
    save_payload(payload)

    print("[weekly_trends] Terminé.")


if __name__ == "__main__":
    main()
