#!/usr/bin/env python3
"""
Pharm'Actus - sync hebdo du chiffre "officines accompagnees" dans le pillar
merch, depuis la RPC Supabase homepage_stats().

POURQUOI CE SCRIPT
Avant le 2026-09-17 ce chiffre etait fige en dur et a derive (202 au lieu de
189 une fois le dedoublonnage "pharmacie X" / "X" corrige en base). Ce script
relit la source a chaque run hebdo
(.github/workflows/sync-pillar-stats.yml) et pousse sur master si besoin.

ARCHITECTURE : pourquoi corriger ICI et pas dans pharmalpha-site
Le pillar merch vit en deux endroits : ce repo (source) et
pharmalpha-site/actus/... (copie servie en prod, regeneree chaque jour par
sync_to_vercel.py). Corriger seulement la copie serait ecrase par la
prochaine sync depuis cette source. Corriger seulement la source laisserait
la prod fausse jusqu'a la sync suivante. Solution retenue : corriger UNIQUEMENT
la source ici, en profitant du pipeline existant -
sync-to-vercel.yml se declenche deja sur tout push master qui touche
articles/** et recopie automatiquement le fichier corrige vers
pharmalpha-site/actus/ en quelques minutes. Pas de deuxieme script necessaire
cote site pour ce fichier precis.

GARDE-FOUS
  - RPC indisponible / reponse invalide -> aucune ecriture, sortie propre (0).
  - Nombre d'occurrences != 5 dans le fichier -> aucune ecriture, echec (1).
    C'est le signal que le contenu editorial a change et que ce script doit
    etre revu.
  - Nouvelle valeur en baisse de plus de 10% vs la valeur en place -> echec
    (1) : une chute brutale est un bug de source, pas une realite.

Usage : python scripts/sync_pillar_stats.py
"""

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PILLAR = ROOT / "articles" / "merchandising" / "merchandising-officine-guide-complet-2026.html"
EXPECTED_OCCURRENCES = 5

# Cle anon publique Supabase (protegee par Row Level Security, pas un
# secret) : meme valeur que pharmalpha-site/inscription/config.js, deja
# committee la, deja utilisee cote client pour ce meme appel RPC.
SUPABASE_URL = "https://pviyggjjyhgsciklulpv.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_xSm6x-8BzPzPhEdfiDlnLA_gNqfBKrY"

# Nombre de 3-4 chiffres suivi de "officines"/"pharmacies", jamais suivi de
# " sur " juste apres. La negation " sur " existe pour une raison precise :
# ce fichier contient la phrase "je les vois dans 9 pharmacies sur 10" - un
# remplacement par motif trop simple y ecrirait "189 pharmacies sur 10". La
# contrainte 3-4 chiffres suffit deja a exclure "9" (1 chiffre), la negation
# " sur " est une seconde barriere si un jour un texte du type "150
# pharmacies sur 200" apparaissait.
STAT_RE = re.compile(r"(?<!\d)(\d{3,4})(\+?)(\s+(?:officines|pharmacies)\b)(?!\s+sur\b)")


def fetch_pharmacies_count():
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/homepage_stats",
        data=b"{}",
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    value = data.get("pharmacies")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"reponse RPC invalide : {data!r}")
    return round(value)


def main():
    try:
        pharmacies = fetch_pharmacies_count()
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as e:
        print(f"[sync-pillar-stats] source indisponible ({e}) - aucune modification, sortie propre.")
        return 0

    content = PILLAR.read_text(encoding="utf-8")
    matches = list(STAT_RE.finditer(content))

    if len(matches) != EXPECTED_OCCURRENCES:
        print(
            f"[sync-pillar-stats] ECHEC : {len(matches)} occurrence(s) trouvee(s) dans "
            f"{PILLAR.name}, {EXPECTED_OCCURRENCES} attendue(s). Contenu editorial change, "
            f"revoir le script avant de reessayer.",
            file=sys.stderr,
        )
        return 1

    current_values = {m.group(1) for m in matches}
    if len(current_values) > 1:
        print(
            f"[sync-pillar-stats] ECHEC : valeurs incoherentes entre occurrences ({current_values}).",
            file=sys.stderr,
        )
        return 1

    current_value = int(current_values.pop())

    if current_value > 0 and pharmacies < current_value * 0.9:
        print(
            f"[sync-pillar-stats] ECHEC : chute de {current_value} a {pharmacies} (> 10%). "
            f"Refuse - probable bug de source, pas une realite.",
            file=sys.stderr,
        )
        return 1

    if pharmacies == current_value:
        print(f"[sync-pillar-stats] deja a jour ({pharmacies}), rien a ecrire.")
        return 0

    def repl(m):
        return f"{pharmacies}{m.group(2)}{m.group(3)}"

    updated = STAT_RE.sub(repl, content)
    PILLAR.write_text(updated, encoding="utf-8")
    print(f"[sync-pillar-stats] {PILLAR.name} : {current_value} -> {pharmacies}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
