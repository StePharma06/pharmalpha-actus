"""
Tests de la transparence IA dans les fenetres de lecture (hub /actus, archives) et la feuille imprimable.

1. PARITE : assets/ia-disclosure.js (le navigateur) doit rendre, pour chaque article, exactement ce que
   update_actus._ai_disclosure ecrit dans le pied de la page (ligne de source, media, lien, paragraphe
   d'information), sur TOUS les articles de articles.json et sur une batterie de cas limites. Deux implementations
   d'un meme texte juridique ne doivent jamais diverger : ce test echoue a la moindre difference.
2. STATIQUE : etiquette (bloc A) ecrite en dur sous le titre de chaque fenetre de lecture, paragraphe generique de
   repli, script charge, ancien rendu "Source : <media>" disparu, mention de print.html.

Les textes attendus sont ceux de l'avis d'Emilie du 2026-10-02 (sections 8.5 et 8.6), mot pour mot.
Necessite node. En local sans node, la parite est ignoree ; en CI (variable CI ou GITHUB_ACTIONS) elle echoue.
Aucun reseau, aucun fichier du depot ecrit.

Lancer : python scripts/test_ia_disclosure.py
"""

import html
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
import update_actus as ua  # noqa: E402

NODE = shutil.which("node")
IN_CI = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
JS = ROOT / "assets" / "ia-disclosure.js"
NBSP = chr(0xA0)
EM, EN = chr(0x2014), chr(0x2013)

RUNNER = """
const fs = require('fs'); const vm = require('vm');
const ctx = vm.createContext({});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
const inputs = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(inputs.map(i => ({ label: ctx.iaDisclosure.sourceLabel(i.source), d: ctx.iaDisclosure.disclosure(i) }))));
"""

# Ligne de source du pied : "<p><strong>LEAD</strong> [<a ...>MEDIA</a> | MEDIA]TAIL</p>" puis "<p>PARAGRAPHE</p>" puis "<p>Editeur ..."
START = re.compile(
    r'^<p><strong>(?P<lead>[^<]+)</strong> (?:<a href="(?P<url>[^"]*)" rel="nofollow noopener">(?P<media>.*?)</a>|(?P<plain>.*?))'
    r'(?P<tail> \(titre et résumé\)\.|\.)</p>\n    ', re.S)


def expected(item):
    """Ce que le pipeline ecrit dans le pied de la page, ramene a la structure du JavaScript."""
    ai = ua._ai_disclosure(item.get("id") or "", item.get("categorie") or "", item.get("source") or "", item.get("source_url") or "")
    foot = ai["footer_html"]
    m = START.match(foot)
    rest = foot[m.end():] if m else foot
    par = re.match(r"<p>(.*?)</p>\n    <p>Éditeur", rest, re.S).group(1)
    media = ""
    if m:
        media = html.unescape(m.group("media") if m.group("media") is not None else m.group("plain"))
    return {
        "lead": m.group("lead") if m else "",
        "media": media,
        "url": html.unescape(m.group("url") or "") if m else "",
        "tail": m.group("tail") if m else "",
        "paragraph": html.unescape(par),
    }


def variant_of(paragraph):
    if paragraph.startswith("Ce texte est une synthèse"):
        return "business"
    if "sans source de presse, puis publié" in paragraph:
        return "lsv"
    if "à partir du titre et du résumé publiés par" in paragraph:
        return "standard"
    return "generic"


def load_articles():
    data = json.loads((ROOT / "articles.json").read_text(encoding="utf-8"))
    arts = data["articles"] if isinstance(data, dict) else data
    return [{"id": a.get("id", ""), "categorie": a.get("categorie", ""), "source": a.get("source", ""), "source_url": a.get("source_url", "")}
            for a in arts if a.get("id")]


EDGE_SOURCES = [
    "", "Pharm'Actus", "Pharm'Alpha", "pharm'alpha", "Pharm" + chr(0x2019) + "Alpha", "Pharm'Actus ", "Pharm'Alphabet", "Pharm'Actus.fr",
    "Le Quotidien du Pharmacien", "Le Moniteur des Pharmacies", "De Hogeweyk, site officiel", "L'Usine Nouvelle", "Libération & Le Monde",
    "Pharm'Actus · Le Monde Santé " + EM + " Ce qui change, Légifrance " + EN + " Texte",
    "Pharm'Actus · Décret n° 2026-832 du 29 août 2026 " + EM + " Légifrance, IQVIA Pharmastat",
    "Pharm'Actus · Arrêté du 3 mars 2026 - Journal officiel, Le Quotidien",
    "Pharm'Actus:Le Monde", "Pharm'Actus - Les Echos - Titre", "Pharm'Actus · " + "mot " * 40, "mot " * 40, "x" * 120,
    "Décret n° 2026-1 " + EM + " Légifrance", "ARRÊTÉ du 1er mai " + EN + " JORF", "Loisirs & Santé " + EM + " Titre", "Loi Neuder - Légifrance",
    "Ordonnance n° 2026-9 " + EM + " Légifrance", "Circulaire DGS " + EN + " Ministère", "Lois de finances " + EM + " Bercy",
    "Le Monde " + EM + " ", " " + EM + " Titre", "A" + NBSP + "B" + NBSP + EM + NBSP + "C", "<b>Le Monde</b>", "L'ANSM & l'HAS; ", ". Le Monde .",
    "Le Figaro" + EM + "Santé", "Les Echos" + " - " + "Pharma", "Le Quotidien - du Pharmacien" + EM + "X",
]
EDGE_URLS = ["", "#", "http://www.exemple.fr/a", "https://www.exemple.fr/a?x=1&y=2", "https://www.exemple.fr/a'b\"c", "javascript:alert(1)",
             "ftp://x", "  https://www.exemple.fr/espaces  ", "HTTPS://MAJUSCULES.FR"]
EDGE_CATEGORIES = ["", "pharma_france", "pharma_monde", "bonne_nouvelle", "avenir_pharma", "business_officine", "lsv", "sante", "inconnue",
                   "business", "business_officine_x", "BUSINESS_OFFICINE", "lsv2", "LSV"]
EDGE_IDS = ["actu_2026_10_03_1", "lsv_2026_10_03", "lsv_x", "x_lsv_1", ""]


def edge_cases():
    out = []
    for i, src in enumerate(EDGE_SOURCES):
        for cat in ("pharma_france", "business_officine", "lsv"):
            out.append({"id": f"actu_2026_10_03_{i}", "categorie": cat, "source": src, "source_url": "https://www.exemple.fr/a?x=1&y=2"})
        out.append({"id": f"actu_2026_10_03_{i}", "categorie": "pharma_france", "source": src, "source_url": ""})
    for url in EDGE_URLS:
        for cat in EDGE_CATEGORIES:
            out.append({"id": "actu_2026_10_03_9", "categorie": cat, "source": "Le Quotidien du Pharmacien", "source_url": url})
    for ident in EDGE_IDS:
        for cat in EDGE_CATEGORIES:
            out.append({"id": ident, "categorie": cat, "source": "Le Monde", "source_url": "https://www.lemonde.fr/x"})
    return out


@unittest.skipUnless(NODE or IN_CI, "node absent : parite JavaScript ignoree en local, obligatoire en CI")
class Parity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if NODE is None:
            raise RuntimeError("node est requis en CI pour comparer assets/ia-disclosure.js au pipeline")
        cls.items = load_articles() + edge_cases()
        r = subprocess.run([NODE, "-e", RUNNER, str(JS)], input=json.dumps(cls.items), capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            raise RuntimeError(r.stderr)
        cls.js = json.loads(r.stdout)

    def test_every_article_and_edge_case_matches_the_pipeline(self):
        self.assertGreater(len(self.items), 1000)
        for item, got in zip(self.items, self.js):
            d, exp = got["d"], expected(item)
            for key in ("lead", "media", "url", "tail", "paragraph"):
                self.assertEqual(d[key], exp[key], f"{key} : {item}")
            self.assertEqual(d["variant"], variant_of(exp["paragraph"]), f"variante : {item}")

    def test_source_label_matches_the_pipeline_for_every_source(self):
        for item, got in zip(self.items, self.js):
            self.assertEqual(got["label"], ua._ai_source_label(item["source"]), repr(item["source"]))

    def test_the_real_data_exercises_business_lsv_and_standard_variants(self):
        seen = {variant_of(expected(i)["paragraph"]) for i in load_articles()}
        self.assertTrue({"business", "lsv", "standard"} <= seen, seen)

    def test_the_javascript_adds_no_dash_and_builds_no_html(self):
        src = JS.read_text(encoding="utf-8")
        self.assertNotIn(EM, src)
        self.assertNotIn(EN, src)
        for forbidden in ("inner" + "HTML", "insertAdjacent" + "HTML", "document" + ".write"):
            self.assertNotIn(forbidden, src)


def page_text(name):
    return (ROOT / name).read_bytes().decode("utf-8").replace("\r\n", "\n")


def plain(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment)).replace(NBSP, " ")).replace(" ,", ",").replace(" .", ".").strip()


class StaticPages(unittest.TestCase):
    GENERIC = re.match(r"<p>(.*?)</p>", ua._ai_disclosure("actu_1970_01_01_1", "", "", "")["footer_html"], re.S).group(1)

    def test_label_is_written_in_the_html_right_under_the_title_of_each_reading_window(self):
        for name in ("index.html", "archives.html"):
            m = re.search(r'<h2 id="modal-title"></h2>\s*<p class="ia-label"><strong>(.*?)</strong></p>', page_text(name), re.S)
            self.assertIsNotNone(m, name)
            self.assertEqual(plain(m.group(1)), ua.AI_LABEL, name)

    def test_generic_paragraph_is_written_in_the_html_as_the_always_true_fallback(self):
        for name in ("index.html", "archives.html"):
            m = re.search(r'<p id="modal-ia-info">(.*?)</p>', page_text(name), re.S)
            self.assertIsNotNone(m, name)
            self.assertEqual(plain(m.group(1)), self.GENERIC, name)

    def test_the_script_is_loaded_and_the_old_source_rendering_of_the_reading_window_is_gone(self):
        for name in ("index.html", "archives.html"):
            t = page_text(name)
            self.assertTrue('<script defer src="assets/ia-disclosure.js"></script>' in t, name)
            window = t[t.index("function openModal"):t.index("function closeModal")]
            self.assertTrue("window.iaDisclosure.render(" in window, name)
            # les cartes de la liste gardent leur ligne "Source" (constat C4 de l'avis, echeance 30 jours) ; la fenetre de lecture, non
            self.assertFalse("Source :" in window, name + " : l'ancien rendu 'Source : <media>' est encore dans la fenetre de lecture")

    def test_reading_windows_sit_above_the_cookie_card_and_the_nav(self):
        # klaro-override.css (depot du site) : carte cookies a 890, nav a 900. En dessous, la carte recouvre le titre et l'etiquette
        # IA de la fenetre a la premiere visite (mesure sur la production le 2026-10-02 : 10 points sur 10 recouverts).
        for name in ("index.html", "archives.html"):
            css = re.search(r"\.modal-overlay \{(.*?)\}", page_text(name), re.S).group(1)
            self.assertGreater(int(re.search(r"z-index:\s*(\d+)", css).group(1)), 900, name)

    # Pages dont la fenetre de lecture porte AUSSI les lignes "Editeur et directeur de la publication" et "Signalez-la"
    # (information complete a chaque exposition, point 143 des lignes directrices). Le hub s'y ajoute avec son prochain push.
    FULL_WINDOW_PAGES = ("archives.html",)

    def test_reading_window_carries_the_editor_and_report_lines_of_the_article_footer(self):
        foot = ua._ai_disclosure("actu_1970_01_01_1", "", "", "")["footer_html"]
        paras = [plain(p) for p in re.findall(r"<p>(.*?)</p>", foot, re.S)]
        editor = next(p for p in paras if p.startswith("Éditeur et directeur de la publication"))
        report = next(p for p in paras if p.startswith("Une erreur ou une imprécision"))
        for name in self.FULL_WINDOW_PAGES:
            m = re.search(r'<p id="modal-ia-info">.*?</p>\s*<p>(.*?)</p>\s*<p>(.*?)</p>\s*</div>', page_text(name), re.S)
            self.assertIsNotNone(m, name)
            self.assertEqual(plain(m.group(1)), editor, name)
            self.assertEqual(plain(m.group(2)), report, name)

    def test_archives_carry_the_banner_before_the_hero_and_a_label_right_above_the_list(self):
        t = page_text("archives.html")
        m = re.search(r'<div class="ia-banner" role="note">\s*<p>(.*?)</p>', t, re.S)
        self.assertIsNotNone(m)
        self.assertEqual(plain(m.group(1)), "Pharm'Actus est généré par une intelligence artificielle et publié automatiquement, sans relecture humaine préalable. "
                                             "Éditeur et directeur de la publication : Stephen Robert. Une erreur ? Signalez-la.")
        self.assertLess(t.index('class="ia-banner"'), t.index('<section class="hero">'))
        m = re.search(r'<p class="ia-list-label">(.*?)</p>\s*<main class="articles-grid"', t, re.S)
        self.assertIsNotNone(m)
        self.assertEqual(plain(m.group(1)), "Textes générés par une intelligence artificielle et publiés automatiquement.")

    def test_the_information_paragraph_sits_above_the_share_row(self):
        for name in ("index.html", "archives.html"):
            t = page_text(name)
            self.assertLess(t.index('id="modal-ia-info"'), t.index('id="modal-share"'), name)

    def test_print_sheet_carries_the_notice_under_the_header_before_the_daily_expression(self):
        t = page_text("print.html")
        m = re.search(r'html \+= "<p class=\\"ia-notice\\">(.*?)</p>";', t)
        self.assertIsNotNone(m)
        self.assertEqual(plain(m.group(1)),
                         "Pharm'Actus est généré par une intelligence artificielle et publié automatiquement, sans relecture humaine préalable. "
                         "Éditeur et directeur de la publication : Stephen Robert. Une erreur ? Écrivez à stephen@pharmalpha.fr.")
        self.assertLess(t.index('class=\\"print-header\\"'), t.index('class=\\"ia-notice\\"'))
        self.assertLess(t.index('class=\\"ia-notice\\"'), t.index("// Expression du jour TOUT EN HAUT"))

    def test_print_notice_is_black_on_white_at_least_10pt_and_never_hidden(self):
        t = page_text("print.html")
        css = re.search(r"\.ia-notice \{(.*?)\}", t, re.S).group(1)
        self.assertRegex(css, r"color:\s*#000")
        self.assertRegex(css, r"background:\s*#fff")
        self.assertGreaterEqual(float(re.search(r"font-size:\s*([\d.]+)pt", css).group(1)), 10)
        self.assertNotRegex(css, r"display:\s*none")
        # regles d'impression qui visent la mention : jamais masquee, jamais sous 10 pt
        printed = t[t.index("@media print"):].split("@media (max-width")[0]
        for rule in re.findall(r"[^{}]*\.ia-notice[^{}]*\{[^}]*\}", printed):
            self.assertNotRegex(rule, r"display:\s*none|visibility:\s*hidden|opacity:\s*0")
            for size in re.findall(r"font-size:\s*([\d.]+)pt", rule):
                self.assertGreaterEqual(float(size), 10)

    def test_pages_add_no_long_dash_in_the_new_texts(self):
        for name in ("index.html", "archives.html", "print.html"):
            for block in re.findall(r'<p class="ia-label">.*?</p>|<p id="modal-ia-info">.*?</p>|ia-notice\\">.*?</p>', page_text(name), re.S):
                self.assertNotIn(EM, block)
                self.assertNotIn(EN, block)


class OtherSurfaces(unittest.TestCase):
    """Pages vendues aux annonceurs, preferences, feuille imprimable : textes de l'avis d'Emilie (8.6 et 8.7), sans signature humaine."""
    IA = "Les textes sont générés par une intelligence artificielle et publiés automatiquement, sans relecture humaine préalable."

    def test_advertiser_page_identifies_the_editor_and_says_the_texts_are_generated(self):
        t = plain(page_text("annonceurs.html"))
        self.assertIn("Un éditeur identifié. Pharm'Actus est édité par Stephen Robert, Docteur en Pharmacie. " + self.IA, t)
        self.assertNotIn("Une signature professionnelle", t)

    def test_media_kit_says_the_texts_are_generated(self):
        self.assertIn("Pharm'Actus est édité par Stephen Robert, Docteur en Pharmacie (Poitiers), également fondateur de Pharm'Alpha. " + self.IA,
                      plain(page_text("media-kit.html")))

    def test_preferences_footer_says_edited_by_not_by(self):
        t = plain(page_text("preferences.html"))
        self.assertIn("· édité par Stephen Robert, Pharm'Alpha", t)
        self.assertNotIn("· par Stephen", t)

    def test_print_card_identifies_the_editor_and_does_not_describe_a_human_daily_work(self):
        t = plain(page_text("print.html"))
        self.assertIn("Docteur en Pharmacie, diplômé d'un Mastère Marketing & Management des Industries de Santé. Éditeur et directeur de la publication de Pharm'Actus.", t)
        self.assertNotIn("Je décrypte", t)

    def test_unserved_email_preview_does_not_bring_the_old_claim_back(self):
        self.assertNotIn("par un pharmacien", page_text("email_template_preview.html"))


if __name__ == "__main__":
    unittest.main()
