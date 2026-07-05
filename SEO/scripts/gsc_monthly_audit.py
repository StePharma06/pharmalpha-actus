"""
gsc_monthly_audit.py — Audit SEO mensuel automatique via Google Search Console API
Pharm'Alpha — Hugo (dev-tech) — 2026-05-28

Usage :
    GSC_SA_KEY_PATH=/path/to/sa-key.json python gsc_monthly_audit.py

Génère : PROJETS/SEO/BASELINE_SEO_AAAA-MM.md au format identique au snapshot manuel.

Dépendances :
    pip install google-api-python-client google-auth
"""

import os
import sys
import json
import datetime
import pathlib

# Console Windows = cp1252 par défaut → force UTF-8 pour les caractères type → / accents
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# --- Validation dépendances au démarrage ---
try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from google.oauth2 import service_account
except ImportError:
    print(
        "ERREUR : dépendances manquantes.\n"
        "Lance : pip install google-api-python-client google-auth\n"
        "puis relance ce script.",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration — tout passe par des variables d'environnement
# ---------------------------------------------------------------------------

# Chemin vers la clé JSON du service account (JAMAIS hardcodé)
SA_KEY_PATH = os.environ.get("GSC_SA_KEY_PATH", "")

# Propriété GSC — on essaie d'abord sc-domain (domain property), fallback URL prefix
SITE_URL_DOMAIN = "sc-domain:pharmalpha.fr"
SITE_URL_PREFIX = "https://pharmalpha.fr/"

# Pages clés à inspecter via urlInspection.index.inspect
KEY_PAGES = [
    "https://pharmalpha.fr/",
    "https://pharmalpha.fr/stephen-robert",
    "https://pharmalpha.fr/actus",
    "https://pharmalpha.fr/presse",
    "https://pharmalpha.fr/consultant-merchandising-officine",
    "https://pharmalpha.fr/formations",
    # Pillars actus
    "https://pharmalpha.fr/actus/articles/merchandising/merchandising-officine-guide-complet-2026.html",
    "https://pharmalpha.fr/actus/articles/audit/audit-pharmacie-guide-complet-2026.html",
]

# Dossier de sortie — relatif à ce fichier (PROJETS/SEO/)
SCRIPT_DIR = pathlib.Path(__file__).parent
SEO_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = SEO_DIR

# Plage de données : 3 mois glissants
TODAY = datetime.date.today()
END_DATE = TODAY.strftime("%Y-%m-%d")
START_DATE = (TODAY - datetime.timedelta(days=90)).strftime("%Y-%m-%d")

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/indexing",  # nécessaire pour urlInspection
]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def build_credentials():
    """Construit les credentials depuis la clé service account.

    Lève une exception explicite si la variable d'env est absente ou si la clé
    est invalide — l'utilisateur sait exactement quoi corriger.
    """
    if not SA_KEY_PATH:
        raise EnvironmentError(
            "Variable d'environnement GSC_SA_KEY_PATH non définie.\n"
            "Consulte PROJETS/SEO/scripts/SETUP_GSC_API.md pour créer la clé "
            "et l'enregistrer dans ton .env local ou GitHub Secret."
        )

    key_path = pathlib.Path(SA_KEY_PATH)
    if not key_path.exists():
        raise FileNotFoundError(
            f"Fichier clé introuvable : {key_path}\n"
            "Vérifie que GSC_SA_KEY_PATH pointe vers le bon chemin."
        )

    credentials = service_account.Credentials.from_service_account_file(
        str(key_path), scopes=SCOPES
    )
    return credentials


# ---------------------------------------------------------------------------
# Détection de la propriété GSC disponible
# ---------------------------------------------------------------------------

def resolve_site_property(webmasters_service):
    """Renvoie la propriété GSC à utiliser (sc-domain: ou URL prefix).

    L'API Search Console distingue deux types de propriétés :
    - Domain property (sc-domain:pharmalpha.fr) — plus large, couvre tous les sous-domaines
    - URL prefix (https://pharmalpha.fr/) — plus restrictif

    On tente d'abord la domain property.
    """
    try:
        sites = webmasters_service.sites().list().execute()
        site_entries = sites.get("siteEntry", [])
        available = {s["siteUrl"] for s in site_entries}

        if SITE_URL_DOMAIN in available:
            print(f"[INFO] Propriété GSC utilisée : {SITE_URL_DOMAIN}")
            return SITE_URL_DOMAIN
        elif SITE_URL_PREFIX in available:
            print(f"[INFO] Propriété GSC utilisée : {SITE_URL_PREFIX}")
            return SITE_URL_PREFIX
        else:
            available_str = "\n  - ".join(sorted(available)) if available else "(aucune)"
            raise PermissionError(
                f"Le service account n'a accès à aucune des propriétés attendues.\n"
                f"Propriétés accessibles :\n  - {available_str}\n\n"
                f"Action requise : ajoute l'email du service account comme utilisateur\n"
                f"dans GSC > Paramètres > Utilisateurs et autorisations (lecture seule).\n"
                f"Consulte PROJETS/SEO/scripts/SETUP_GSC_API.md."
            )
    except HttpError as e:
        raise RuntimeError(f"Erreur API GSC (sites.list) : {e}") from e


# ---------------------------------------------------------------------------
# Pull 1 — Search Analytics (queries, pages, devices)
# ---------------------------------------------------------------------------

def fetch_search_analytics(webmasters_service, site_property):
    """Retourne un dict avec top queries, top pages et répartition devices."""

    def query(dimensions, row_limit=50):
        body = {
            "startDate": START_DATE,
            "endDate": END_DATE,
            "dimensions": dimensions,
            "rowLimit": row_limit,
            "startRow": 0,
        }
        try:
            resp = (
                webmasters_service.searchanalytics()
                .query(siteUrl=site_property, body=body)
                .execute()
            )
            return resp.get("rows", [])
        except HttpError as e:
            print(f"[WARN] searchanalytics.query({dimensions}) : {e}", file=sys.stderr)
            return []

    top_queries = query(["query"])
    top_pages = query(["page"])
    by_device = query(["device"], row_limit=10)

    # Totaux globaux (sans dimension = agrégé)
    totals_body = {
        "startDate": START_DATE,
        "endDate": END_DATE,
        "rowLimit": 1,
    }
    try:
        totals_resp = (
            webmasters_service.searchanalytics()
            .query(siteUrl=site_property, body=totals_body)
            .execute()
        )
        totals_rows = totals_resp.get("rows", [])
        totals = totals_rows[0] if totals_rows else {}
    except HttpError as e:
        print(f"[WARN] searchanalytics totals : {e}", file=sys.stderr)
        totals = {}

    return {
        "top_queries": top_queries,
        "top_pages": top_pages,
        "by_device": by_device,
        "totals": totals,
    }


# ---------------------------------------------------------------------------
# Pull 2 — Sitemaps
# ---------------------------------------------------------------------------

def fetch_sitemaps(webmasters_service, site_property):
    """Retourne la liste des sitemaps soumis avec leur statut."""
    try:
        resp = webmasters_service.sitemaps().list(siteUrl=site_property).execute()
        return resp.get("sitemap", [])
    except HttpError as e:
        print(f"[WARN] sitemaps.list : {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Pull 3 — URL Inspection (indexation par page)
# ---------------------------------------------------------------------------

def fetch_url_inspections(inspection_service, site_property):
    """Inspecte les pages clés via urlInspection.index.inspect.

    L'API coverage bulk n'est pas exposée publiquement.
    urlInspection donne le statut Google pour chaque URL individuellement.

    Limite API : 2 000 requêtes/jour/projet GCP.
    Avec 8 pages clés on est très loin de la limite.
    """
    results = {}
    for url in KEY_PAGES:
        body = {
            "inspectionUrl": url,
            "siteUrl": site_property,
            "languageCode": "fr",
        }
        try:
            resp = (
                inspection_service.urlInspection()
                .index()
                .inspect(body=body)
                .execute()
            )
            result = resp.get("inspectionResult", {})
            index_result = result.get("indexStatusResult", {})
            results[url] = {
                "verdict": index_result.get("verdict", "UNKNOWN"),
                "coverage_state": index_result.get("coverageState", ""),
                "robots_txt_state": index_result.get("robotsTxtState", ""),
                "indexing_state": index_result.get("indexingState", ""),
                "last_crawl_time": index_result.get("lastCrawlTime", ""),
                "page_fetch_state": index_result.get("pageFetchState", ""),
                "canonical_url": index_result.get("googleCanonical", url),
            }
        except HttpError as e:
            print(f"[WARN] urlInspection {url} : {e}", file=sys.stderr)
            results[url] = {"verdict": "API_ERROR", "detail": str(e)}

    return results


# ---------------------------------------------------------------------------
# Formatage du rapport markdown
# ---------------------------------------------------------------------------

def fmt_pct(val):
    return f"{val * 100:.2f}%"


def fmt_pos(val):
    return f"{val:.1f}"


def fmt_clics(val):
    return str(int(round(val)))


def render_markdown(analytics, sitemaps, url_inspections, site_property):
    """Génère le rapport markdown au même format que BASELINE_SEO_2026-05.md."""

    month_label = TODAY.strftime("%Y-%m")
    date_label = TODAY.strftime("%Y-%m-%d")

    totals = analytics.get("totals", {})
    total_clicks = int(round(totals.get("clicks", 0)))
    total_impressions = int(round(totals.get("impressions", 0)))
    avg_position = totals.get("position", 0)

    # Top pages
    top_pages = analytics.get("top_pages", [])[:10]
    pages_md_rows = []
    for i, row in enumerate(top_pages, 1):
        keys = row.get("keys", ["?"])
        page = keys[0] if keys else "?"
        # Raccourcir l'URL pour lisibilité
        short = page.replace("https://pharmalpha.fr", "")
        clicks = fmt_clics(row.get("clicks", 0))
        impressions = fmt_clics(row.get("impressions", 0))
        ctr = fmt_pct(row.get("ctr", 0))
        pos = fmt_pos(row.get("position", 0))
        pages_md_rows.append(f"{i}. `{short}` — {clicks} clics / {impressions} imp / {ctr} CTR / pos {pos}")

    # Top requêtes
    top_queries = analytics.get("top_queries", [])[:15]
    queries_md_rows = []
    for row in top_queries:
        keys = row.get("keys", ["?"])
        q = keys[0] if keys else "?"
        clicks = fmt_clics(row.get("clicks", 0))
        impressions = fmt_clics(row.get("impressions", 0))
        pos = fmt_pos(row.get("position", 0))
        queries_md_rows.append(f"- `{q}` — {clicks} clics / {impressions} imp / pos {pos}")

    # Appareils
    by_device = analytics.get("by_device", [])
    device_rows = []
    for row in by_device:
        keys = row.get("keys", ["?"])
        dev = keys[0] if keys else "?"
        clicks = fmt_clics(row.get("clicks", 0))
        impressions = fmt_clics(row.get("impressions", 0))
        ctr = fmt_pct(row.get("ctr", 0))
        device_rows.append(f"| {dev} | {clicks} | {impressions} | {ctr} |")

    # Sitemaps
    sitemap_rows = []
    for sm in sitemaps:
        sm_url = sm.get("path", "?").split("/")[-1]
        discovered = sm.get("contents", [{}])[0].get("submitted", "?") if sm.get("contents") else "?"
        indexed = sm.get("contents", [{}])[0].get("indexed", "?") if sm.get("contents") else "?"
        errors = sm.get("errors", 0)
        warnings = sm.get("warnings", 0)
        last_submitted = sm.get("lastSubmitted", "?")[:10] if sm.get("lastSubmitted") else "?"
        status = "OK" if errors == 0 else f"ERREURS ({errors})"
        sitemap_rows.append(f"| `{sm_url}` | {discovered} | {indexed} | {status} | {last_submitted} |")

    # URL Inspection
    inspection_rows = []
    verdict_icons = {
        "PASS": "INDEXEE",
        "FAIL": "EXCLUE",
        "NEUTRAL": "NEUTRE",
        "UNKNOWN": "INCONNU",
        "API_ERROR": "ERREUR API",
    }
    for url, data in url_inspections.items():
        short = url.replace("https://pharmalpha.fr", "") or "/"
        verdict = data.get("verdict", "UNKNOWN")
        label = verdict_icons.get(verdict, verdict)
        state = data.get("coverage_state", "")
        crawl = data.get("last_crawl_time", "")[:10] if data.get("last_crawl_time") else "?"
        inspection_rows.append(f"| `{short}` | {label} | {state} | {crawl} |")

    # Assemblage du rapport
    lines = [
        f"# BASELINE SEO pharmalpha.fr — Snapshot mensuel",
        f"",
        f"> Généré automatiquement le {date_label} via l'API Google Search Console.",
        f"> Propriété GSC : `{site_property}`",
        f"> Période données : {START_DATE} → {END_DATE} (90 jours glissants).",
        f"> Source script : `PROJETS/SEO/scripts/gsc_monthly_audit.py`",
        f"",
        f"---",
        f"",
        f"## Snapshot {date_label}",
        f"",
        f"### Performances globales (GSC, 90 jours)",
        f"| Métrique | Valeur |",
        f"|---|---|",
        f"| Clics totaux | **{total_clicks}** |",
        f"| Impressions totales | **{total_impressions}** |",
        f"| Position moyenne | {fmt_pos(avg_position)} |",
        f"",
        f"**Top pages (clics / impressions / CTR / position)**",
    ]
    lines += pages_md_rows or ["*Aucune donnée disponible.*"]
    lines += [
        f"",
        f"**Top requêtes (clics / impressions / position)**",
    ]
    lines += queries_md_rows or ["*Aucune donnée disponible.*"]
    lines += [
        f"",
        f"**Répartition par appareil**",
        f"| Appareil | Clics | Impressions | CTR |",
        f"|---|---|---|---|",
    ]
    lines += device_rows or ["| *Aucune donnée* | — | — | — |"]
    lines += [
        f"",
        f"---",
        f"",
        f"### Sitemaps (GSC › Sitemaps)",
        f"| Sitemap | URLs soumises | URLs indexées | État | Dernière lecture |",
        f"|---|---|---|---|---|",
    ]
    lines += sitemap_rows or ["| *Aucun sitemap* | — | — | — | — |"]
    lines += [
        f"",
        f"---",
        f"",
        f"### Indexation pages clés (urlInspection)",
        f"| Page | Verdict Google | État couverture | Dernier crawl |",
        f"|---|---|---|---|",
    ]
    lines += inspection_rows or ["| *Aucune inspection* | — | — | — |"]
    lines += [
        f"",
        f"---",
        f"",
        f"## Priorités issues de ce snapshot",
        f"*(À compléter par Marc après lecture du rapport.)*",
        f"",
        f"## Méthode de suivi",
        f"- Comparer chaque mois : clics, impressions, nb pages indexées, position `stephen robert` + requêtes merch cibles, CWV.",
        f"- Objectifs T2 2026 : 200+ pages indexées, top 30 sur 10 mots-clés, 5 000+ impressions/mois.",
        f"- Script : `python gsc_monthly_audit.py` (ou GitHub Actions `gsc-monthly.yml` le 1er de chaque mois).",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    print(f"[gsc_monthly_audit] Démarrage — {TODAY.isoformat()}")
    print(f"[gsc_monthly_audit] Période analysée : {START_DATE} → {END_DATE}")

    # 1. Auth
    print("[1/5] Authentification service account...")
    try:
        credentials = build_credentials()
    except (EnvironmentError, FileNotFoundError) as e:
        print(f"\nERREUR AUTH :\n{e}", file=sys.stderr)
        sys.exit(1)

    # 2. Construction des clients API
    print("[2/5] Construction des clients API GSC...")
    try:
        webmasters_service = build("webmasters", "v3", credentials=credentials)
        # urlInspection est dans l'API searchconsole v1
        inspection_service = build("searchconsole", "v1", credentials=credentials)
    except Exception as e:
        print(f"\nERREUR construction client API : {e}", file=sys.stderr)
        sys.exit(1)

    # 3. Résolution de la propriété GSC
    print("[3/5] Détection de la propriété GSC...")
    try:
        site_property = resolve_site_property(webmasters_service)
    except (PermissionError, RuntimeError) as e:
        print(f"\nERREUR PROPRIÉTÉ GSC :\n{e}", file=sys.stderr)
        sys.exit(1)

    # 4. Pull des données
    print("[4/5] Pull des données GSC...")
    print("  → Search Analytics (queries, pages, devices)...")
    analytics = fetch_search_analytics(webmasters_service, site_property)

    print("  → Sitemaps...")
    sitemaps = fetch_sitemaps(webmasters_service, site_property)

    print(f"  → URL Inspection ({len(KEY_PAGES)} pages clés)...")
    url_inspections = fetch_url_inspections(inspection_service, site_property)

    # 5. Génération du rapport
    print("[5/5] Génération du rapport markdown...")
    month_label = TODAY.strftime("%Y-%m")
    output_path = OUTPUT_DIR / f"BASELINE_SEO_{month_label}.md"

    # On ne surécrit pas un rapport existant sans avertir
    if output_path.exists():
        backup_path = OUTPUT_DIR / f"BASELINE_SEO_{month_label}_prev_{TODAY.strftime('%d')}.md"
        output_path.rename(backup_path)
        print(f"  [INFO] Rapport existant sauvegardé : {backup_path.name}")

    report_md = render_markdown(analytics, sitemaps, url_inspections, site_property)
    output_path.write_text(report_md, encoding="utf-8")

    print(f"\n[OK] Rapport généré : {output_path}")
    print(f"     {len(analytics.get('top_queries', []))} requêtes | {len(analytics.get('top_pages', []))} pages | {len(sitemaps)} sitemaps | {len(url_inspections)} URLs inspectées")


if __name__ == "__main__":
    main()
