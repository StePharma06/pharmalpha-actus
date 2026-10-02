"""
Tests du gabarit des pages Pharm'Actus et du bandeau de l'email (AI Act art. 50).

Les textes attendus sont ceux de l'avis d'Emilie du 2026-10-02, sujet 1, blocs A a D, MOT POUR MOT :
si un de ces tests casse parce qu'on a reformule un texte, c'est voulu, il faut son accord.
Les liens "journal des corrections" et "Comment Pharm'Actus est produit" sont absents a dessein
tant que ces pages n'existent pas.

Aucun reseau, aucun fichier du depot ecrit. Importe update_actus, qui a besoin de anthropic et
feedparser (installes dans daily-update.yml).

Lancer : python scripts/test_article_template.py
"""

import html
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_actus as ua  # noqa: E402

EM, EN = chr(0x2014), chr(0x2013)
LABEL = "Texte généré par une intelligence artificielle et publié automatiquement."
PRESS_SENTENCE = ("Ce texte a été généré par une intelligence artificielle à partir du titre et du résumé "
                  "publiés par {src}, puis publié automatiquement, sans relecture humaine préalable.")
NO_SOURCE_SENTENCE = ("Ce texte a été généré par une intelligence artificielle sans source de presse unique, "
                      "puis publié automatiquement, sans relecture humaine préalable.")
LSV_SENTENCE = NO_SOURCE_SENTENCE + " Les faits historiques sont à vérifier avant d'être cités."
TAIL = ("Il peut contenir des erreurs : pour toute information réglementaire ou chiffrée, reportez-vous à la "
        "source officielle. Il ne constitue ni un avis médical ou pharmaceutique, ni un conseil juridique ou fiscal.")
EDITOR = ("Éditeur et directeur de la publication : Stephen Robert, Docteur en Pharmacie "
          "(entreprise individuelle Pharm'Alpha, SIREN 910 877 356), stephen@pharmalpha.fr, mentions légales.")
BANNER = ("Pharm'Actus est généré par une intelligence artificielle et publié automatiquement, sans relecture "
          "humaine préalable. Éditeur et directeur de la publication : Stephen Robert. Une erreur ? Signalez-la.")
FORBIDDEN = ["rédigé par", "redige par", "article:author", "stephen-robert", "#stephen", "responsabilité éditoriale",
             "journal des corrections", "Comment Pharm'Actus est produit", '"Person"', "reviewedBy", '"editor"',
             '"contributor"']


def page(article_id="actu_2026_10_02_1", categorie="pharma_france", source="Le Quotidien du Pharmacien",
         source_url="https://www.exemple.fr/article?a=1&b=2", date_modified=""):
    return ua._build_article_page_html(
        article_id=article_id, titre_raw="Titre de test", resume_raw="Résumé de test.", image_url="",
        date_str="2026-10-02", categorie=categorie, full_text_raw="Premier paragraphe.\n\nSecond paragraphe.",
        source_url=source_url, source_name=source, date_modified_str=date_modified,
    )


def footer_text(p):
    foot = p[p.index('<footer class="article-footer">'):p.index("</footer>")]
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", foot))).replace(" ,", ",").replace(" .", ".")


def jsonld(p):
    return json.loads(re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', p, re.S).group(1))


class Label(unittest.TestCase):
    def test_label_sits_between_title_and_lead_on_every_variant(self):
        for p in (page(), page("lsv_2026_10_02", "lsv", "Pharm'Alpha", ""), page(source="Pharm'Actus", source_url="")):
            self.assertEqual(p.count(LABEL), 1)
            self.assertLess(p.index("</h1>"), p.index(LABEL))
            self.assertLess(p.index(LABEL), p.index('<p class="article-lead">'))


class Footer(unittest.TestCase):
    def test_press_variant_is_verbatim(self):
        t = footer_text(page())
        self.assertIn("Point de départ : Le Quotidien du Pharmacien (titre et résumé).", t)
        self.assertIn(PRESS_SENTENCE.format(src="Le Quotidien du Pharmacien") + " " + TAIL, t)
        self.assertIn(EDITOR, t)
        self.assertIn("Une erreur ou une imprécision ? Signalez-la à stephen@pharmalpha.fr.", t)
        self.assertIn("Découvrir les formations Pharm'Alpha", t)

    def test_press_source_is_a_link_and_url_is_escaped(self):
        p = page()
        self.assertIn('<a href="https://www.exemple.fr/article?a=1&amp;b=2" rel="nofollow noopener">Le Quotidien du Pharmacien</a>', p)
        self.assertIn('href="https://pharmalpha.fr/mentions-legales"', p)
        self.assertIn('href="https://pharmalpha.fr/formations"', p)

    def test_lsv_variant_has_no_point_de_depart(self):
        t = footer_text(page("lsv_2026_10_02", "lsv", "Pharm'Alpha", ""))
        self.assertNotIn("Point de départ", t)
        self.assertIn(LSV_SENTENCE + " " + TAIL, t)
        self.assertIn(EDITOR, t)

    def test_article_without_named_media_gets_the_sentence_without_history(self):
        t = footer_text(page(source="Pharm'Actus", source_url=""))
        self.assertNotIn("Point de départ", t)
        self.assertIn(NO_SOURCE_SENTENCE + " " + TAIL, t)
        self.assertNotIn("faits historiques", t)

    def test_no_dead_link_when_the_source_has_no_url(self):
        p = page(source_url="")
        self.assertNotIn('href="#"', p)
        self.assertIn("Point de départ : Le Quotidien du Pharmacien (titre et résumé).", footer_text(p))
        self.assertNotIn("isBasedOn", jsonld(p))

    def test_business_composite_source_keeps_the_first_media_only(self):
        src = "Pharm'Actus · Le Monde Santé " + EM + " Ce qui change, Légifrance " + EN + " Texte"
        p = page("actu_2026_10_02_5", "business_officine", src, "https://www.lemonde.fr/x")
        self.assertIn("Point de départ : Le Monde Santé (titre et résumé).", footer_text(p))
        self.assertEqual(jsonld(p)["creditText"], "Texte généré par une intelligence artificielle à partir du titre et du résumé publiés par Le Monde Santé")
        self.assertNotIn("Pharm'Actus ·", footer_text(p))

    def test_official_text_first_in_a_composite_source_gives_the_media_after_the_dash(self):
        src = "Pharm'Actus · Décret n° 2026-832 du 29 août 2026 " + EM + " Légifrance, IQVIA Pharmastat"
        self.assertEqual(ua._ai_source_label(src), "Légifrance")

    def test_plain_names_are_kept_whole_commas_included(self):
        self.assertEqual(ua._ai_source_label("De Hogeweyk, site officiel"), "De Hogeweyk, site officiel")
        self.assertEqual(ua._ai_source_label("Le Quotidien du Pharmacien"), "Le Quotidien du Pharmacien")
        self.assertEqual(ua._ai_source_label("Pharm'Actus"), "")
        self.assertEqual(ua._ai_source_label(""), "")

    def test_long_labels_are_cut_on_a_word(self):
        self.assertLessEqual(len(ua._ai_source_label("Pharm'Actus · " + "mot " * 40)), 90)
        self.assertFalse(ua._ai_source_label("Pharm'Actus · " + "mot " * 40).endswith("mo"))


class JsonLd(unittest.TestCase):
    def test_author_is_the_organization_and_credit_matches_the_visible_text(self):
        ld = jsonld(page())
        self.assertEqual(ld["author"], {"@type": "Organization", "name": "Pharm'Actus", "url": "https://pharmalpha.fr/actus"})
        self.assertEqual(ld["publisher"], {"@id": "https://pharmalpha.fr/#org"})
        self.assertEqual(ld["creditText"], "Texte généré par une intelligence artificielle à partir du titre et du résumé publiés par Le Quotidien du Pharmacien")
        self.assertEqual(ld["isBasedOn"], "https://www.exemple.fr/article?a=1&b=2")

    def test_lsv_credit_and_no_isbasedon(self):
        ld = jsonld(page("lsv_2026_10_02", "lsv", "Pharm'Alpha", ""))
        self.assertEqual(ld["creditText"], "Texte généré par une intelligence artificielle sans source de presse unique")
        self.assertNotIn("isBasedOn", ld)

    def test_no_person_editor_reviewedby_or_contributor_anywhere(self):
        def walk(o):
            if isinstance(o, dict):
                yield o
                for v in o.values():
                    yield from walk(v)
            elif isinstance(o, list):
                for v in o:
                    yield from walk(v)
        for p in (page(), page("lsv_2026_10_02", "lsv", "Pharm'Alpha", "")):
            for node in walk(jsonld(p)):
                self.assertNotEqual(node.get("@type"), "Person")
                for key in ("editor", "reviewedBy", "contributor", "creator", "accountablePerson"):
                    self.assertNotIn(key, node)

    def test_date_modified_follows_the_article_and_is_not_touched_by_the_attribution(self):
        self.assertEqual(jsonld(page())["dateModified"], "2026-10-02T06:00:00+02:00")
        self.assertEqual(jsonld(page(date_modified="2026-09-01"))["dateModified"], "2026-09-01T06:00:00+02:00")
        self.assertEqual(jsonld(page(date_modified="2026-09-01"))["datePublished"], "2026-10-02T06:00:00+02:00")


class NoSignature(unittest.TestCase):
    def test_nothing_signs_the_page_with_a_person(self):
        for p in (page(), page("lsv_2026_10_02", "lsv", "Pharm'Alpha", ""), page(source="Pharm'Actus", source_url="")):
            for bad in FORBIDDEN:
                self.assertNotIn(bad, p.replace("stephen@pharmalpha.fr", ""), bad)

    def test_template_adds_no_long_or_short_dash(self):
        for p in (page(), page("lsv_2026_10_02", "lsv", "Pharm'Alpha", "")):
            self.assertNotIn(EM, p)
            self.assertNotIn(EN, p)


class Email(unittest.TestCase):
    ARTICLES = [
        {"id": "actu_2026_10_02_1", "titre": "Titre un", "resume": "Résumé un.", "categorie": "pharma_france", "source": "Le Quotidien du Pharmacien", "badge_label": "Pharma France"},
        {"id": "lsv_2026_10_02", "titre": "Histoire", "resume": "Résumé LSV.", "categorie": "lsv", "source": "Pharm'Alpha", "badge_label": "Le Saviez-Vous"},
    ]

    def setUp(self):
        self.mail = ua.build_newsletter_html(self.ARTICLES, custom_intro="Intro de test.")

    def test_banner_text_is_verbatim_and_comes_first(self):
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", self.mail)))
        self.assertIn(BANNER, text)
        i = self.mail.index("est g&eacute;n&eacute;r&eacute; par une intelligence artificielle")
        # "Expression du jour" depend d'un fichier de donnees : on ne l'exige pas, mais s'il est la il vient apres
        for later in ("logo_pharmactus.png", "Expression du jour", "Intro de test.", "Titre un", "unsubscribe"):
            if later == "Expression du jour" and later not in self.mail:
                continue
            self.assertGreater(self.mail.index(later), i, later)

    def test_old_footer_mention_is_gone(self):
        for old in ("responsabilit&eacute; &eacute;ditoriale", "assistance d'outils d'intelligence artificielle", "elle sera corrig"):
            self.assertNotIn(old, self.mail)

    def test_banner_is_readable_and_has_no_dash(self):
        self.assertRegex(self.mail, r'<td style="background:#fff7ed;[^"]*font-size:13px;[^"]*color:#1a1a1a;')
        self.assertNotIn(EM, self.mail)
        self.assertNotIn(EN, self.mail)


if __name__ == "__main__":
    unittest.main()
