#!/usr/bin/env python3
"""
test_image_quality.py — Dry-run du pipeline QA images sur les actus existantes.

Charge les 6 actus de la semaine W17 (déjà publiées sur Pharm'Actus avec leurs vraies
image_keywords), et teste le pipeline pick_best_image() sans toucher au repo en prod.

Output: rapport texte montrant pour chaque actu :
- Mots-cles utilises
- Candidats Pexels (URL + verdict cohérence Haiku)
- Décision finale : pexels (kept) / pexels-alt / grok / stock
- MD5 doublons détectés

Usage:
    XAI_API_KEY=xai-... ANTHROPIC_API_KEY=sk-ant-... python test_image_quality.py
"""
import os
import sys
import json
from pathlib import Path

# Permet d'importer les fonctions de update_actus sans run le main
sys.path.insert(0, str(Path(__file__).parent))

# Import propre
import update_actus as ua

# Cas de test : les 6 articles W17 que Stephen a vus produire des doublons + images inadaptees
TEST_ARTICLES = [
    {
        "id": "actu_2026_04_20_1",
        "titre": "150 millions d'euros pour transformer des officines en Maisons France Sante",
        "resume": "L'Etat debloque 150 millions pour creer le reseau France Sante en 2026. Les pharmacies d'officine, quand elles sont le dernier maillon de soins dans leur commune, peuvent decrocher le label.",
        "image_keywords": "rural pharmacy french village",
        "categorie": "pharmacie_france",
    },
    {
        "id": "actu_2026_04_22_1",
        "titre": "L'USPO devoile sa recette pour economiser 2 milliards sans casser l'officine",
        "resume": "Face a l'objectif de 2 milliards d'economies sur l'Assurance Maladie, l'USPO sort du bois avec des propositions concretes : substitution renforcee, deprescription, optimisation des volumes.",
        "image_keywords": "pharmacy savings money",  # MAUVAIS keywords (qui ont produit le medecin/dollars)
        "categorie": "pharmacie_france",
    },
    {
        "id": "actu_2026_04_23_1",
        "titre": "6 800 euros par an : les nouvelles missions qui font gonfler ta caisse",
        "resume": "Pharmactiv devoile ses chiffres : vaccination, bilans, accompagnement. Ces missions peuvent rapporter jusqu'a 6 800 euros annuels a l'officine.",
        "image_keywords": "pharmacy consultation",  # bons keywords
        "categorie": "pharmacie_france",
    },
    {
        "id": "actu_2026_04_25_1",
        "titre": "Bug Scor : les ordonnances numeriques encore plantees jusqu'au 30 avril",
        "resume": "Le bug de teletransmission des pieces justificatives via Scor continue de pourrir la vie aux officines. La Cnam confirme : c'est de leur cote, pas le votre.",
        "image_keywords": "computer error pharmacy",
        "categorie": "pharmacie_france",
    },
    {
        "id": "actu_2026_04_26_1",
        "titre": "Novo Nordisk casse les prix d'Ozempic et Wegovy de 35 a 50%",
        "resume": "Le geant danois annonce une baisse historique pour 2027 aux Etats-Unis : Wegovy passe a 675$. Trump et la pression politique ont eu raison de la strategie tarifaire.",
        "image_keywords": "ozempic semaglutide injection",
        "categorie": "pharmacie_monde",
    },
    {
        "id": "lsv_2026_04_21",
        "titre": "Le saviez-vous ? La penicilline a failli finir a la poubelle",
        "resume": "En 1928, Alexander Fleming decouvre par accident le premier antibiotique de l'histoire. Mais il a fallu attendre 12 ans et une guerre mondiale pour que sa trouvaille revolutionne la medecine.",
        "image_keywords": "penicillin mold petri dish",
        "categorie": "lsv",
    },
]


def main():
    print("=" * 70)
    print("DRY-RUN : Pipeline QA images Pharm'Actus")
    print("=" * 70)
    print()

    # Init Claude client (pour validation coherence)
    try:
        import anthropic
        client = anthropic.Anthropic()
        print(f"[OK] Anthropic client initialise (validation coherence active)")
    except Exception as e:
        print(f"[WARN] Anthropic client KO ({e}) - test partiel sans validation Claude")
        client = None

    # Init recent_md5s avec un set vide pour simuler une 1ere semaine "propre"
    # (on detectera les doublons INTRA cette session)
    recent_md5s = set()

    print(f"[INFO] XAI_API_KEY: {'PRESENT' if os.environ.get('XAI_API_KEY') else 'ABSENT'} (Grok fallback)")
    print(f"[INFO] {len(TEST_ARTICLES)} articles W17 a tester")
    print()

    # Override ASSETS_DIR vers un dossier de test isole pour ne pas polluer le repo
    test_assets = Path(__file__).parent.parent / "test_output" / "assets_dryrun"
    test_assets.mkdir(parents=True, exist_ok=True)
    ua.ASSETS_DIR = test_assets

    results = []
    for idx, article in enumerate(TEST_ARTICLES, 1):
        article_id = article["id"]
        print(f"--- [{idx}/{len(TEST_ARTICLES)}] {article['titre'][:60]}")
        print(f"    keywords: {article['image_keywords']}")

        img_url, cdn_url, source = ua.pick_best_image(
            article, article_id, recent_md5s, claude_client=client
        )
        results.append({
            "id": article_id,
            "title": article["titre"][:80],
            "img_url": img_url,
            "source": source,
        })
        print(f"    => SOURCE FINALE: {source.upper()}")
        print(f"    => CDN: {cdn_url[:90]}")
        print()

    print("=" * 70)
    print("RESUME")
    print("=" * 70)
    by_source = {}
    for r in results:
        by_source.setdefault(r["source"], 0)
        by_source[r["source"]] += 1
    for src, n in sorted(by_source.items()):
        print(f"  {src or 'AUCUN':12s}: {n}")
    print()
    print(f"Doublons detectes intra-session: {len(recent_md5s)} MD5 uniques pour {len(TEST_ARTICLES)} articles")
    print(f"  (si {len(recent_md5s)} < {len(TEST_ARTICLES)}, des doublons ont ete evites)")
    print()
    print(f"Images de test sauvees dans: {test_assets}")


if __name__ == "__main__":
    main()
