"""
Tests du gabarit des pages Pharm'Actus et du bandeau de l'email (AI Act art. 50).

Les textes attendus sont ceux de l'avis d'Emilie du 2026-10-02, MOT POUR MOT : sujet 1, blocs A a D, puis
section 8 (variante Business, variante LSV, variante generique, creditText, ordre de selection).
Si un de ces tests casse parce qu'on a reformule un texte, c'est voulu, il faut son accord.
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
GENERIC_SENTENCE = ("Ce texte a été généré par une intelligence artificielle, puis publié automatiquement, "
                    "sans relecture humaine préalable.")
LSV_SENTENCE = ("Ce texte a été généré par une intelligence artificielle, sans source de presse, puis publié "
                "automatiquement, sans relecture humaine préalable. Les faits historiques sont à vérifier avant "
                "d'être cités.")
TAIL = ("Il peut contenir des erreurs : pour toute information réglementaire ou chiffrée, reportez-vous à la "
        "source officielle. Il ne constitue ni un avis médical ou pharmaceutique, ni un conseil juridique ou fiscal.")
BUSINESS_PARAGRAPH = (
    "Ce texte est une synthèse générée par une intelligence artificielle à partir de titres et de résumés d'articles "
    "de presse, puis publiée automatiquement, sans relecture humaine préalable. Il peut contenir des informations qui "
    "ne figurent dans aucune de ces sources, y compris des chiffres et des références, et les sources citées en fin de "
    "texte ont été indiquées par l'intelligence artificielle sans avoir été vérifiées. Pour toute information "
    "réglementaire, chiffrée ou financière, reportez-vous à la source officielle. Il ne constitue ni un avis médical "
    "ou pharmaceutique, ni un conseil juridique, fiscal ou de gestion.")
BUSINESS_FIRST_SOURCE = "Première source indiquée par l'intelligence artificielle : {src}."
EDITOR = ("Éditeur et directeur de la publication : Stephen Robert, Docteur en Pharmacie "
          "(entreprise individuelle Pharm'Alpha, SIREN 910 877 356), stephen@pharmalpha.fr, mentions légales.")
REPORT = "Une erreur ou une imprécision ? Signalez-la à stephen@pharmalpha.fr."
BANNER = ("Pharm'Actus est généré par une intelligence artificielle et publié automatiquement, sans relecture "
          "humaine préalable. Éditeur et directeur de la publication : Stephen Robert. Une erreur ? Signalez-la.")
CREDIT = {
    "press": "Texte généré par une intelligence artificielle à partir du titre et du résumé publiés par {src}",
    "business": "Texte généré par une intelligence artificielle à partir de titres et de résumés d'articles de presse",
    "lsv": "Texte généré par une intelligence artificielle, sans source de presse",
    "generic": "Texte généré par une intelligence artificielle",
}
FORBIDDEN = ["rédigé par", "redige par", "article:author", "stephen-robert", "#stephen", "responsabilité éditoriale",
             "journal des corrections", "Comment Pharm'Actus est produit", '"Person"', "reviewedBy", '"editor"',
             '"contributor"', "sans source de presse unique"]
# Avis d'Emilie, section 8.4 point 6 : ne rien ajouter qui annonce une politique editoriale ou une entite inexistante.
FORBIDDEN_JSONLD = ["parentOrganization", "legalName", "taxID", "address", "NewsMediaOrganization",
                    "publishingPrinciples", "correctionsPolicy"]

COMPOSITE = "Pharm'Actus · Le Monde Santé " + EM + " Ce qui change, Légifrance " + EN + " Texte"
MONDE_URL = "https://www.lemonde.fr/x"


def page(article_id="actu_2026_10_02_1", categorie="pharma_france", source="Le Quotidien du Pharmacien",
         source_url="https://www.exemple.fr/article?a=1&b=2", date_modified=""):
    return ua._build_article_page_html(
        article_id=article_id, titre_raw="Titre de test", resume_raw="Résumé de test.", image_url="",
        date_str="2026-10-02", categorie=categorie, full_text_raw="Premier paragraphe.\n\nSecond paragraphe.",
        source_url=source_url, source_name=source, date_modified_str=date_modified,
    )


def business(source=COMPOSITE, source_url=MONDE_URL):
    return page("actu_2026_10_02_5", "business_officine", source, source_url)


def lsv(source="Pharm'Alpha", source_url=""):
    return page("lsv_2026_10_02", "lsv", source, source_url)


def footer_text(p):
    foot = p[p.index('<footer class="article-footer">'):p.index("</footer>")]
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", foot))).replace(" ,", ",").replace(" .", ".")


def jsonld(p):
    return json.loads(re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', p, re.S).group(1))


class Label(unittest.TestCase):
    def test_label_sits_between_title_and_lead_on_every_variant(self):
        for p in (page(), lsv(), business(), business("Pharm'Actus", ""), page(source="Pharm'Actus", source_url="")):
            self.assertEqual(p.count(LABEL), 1)
            self.assertLess(p.index("</h1>"), p.index(LABEL))
            self.assertLess(p.index(LABEL), p.index('<p class="article-lead">'))


class Footer(unittest.TestCase):
    def test_press_variant_is_verbatim(self):
        t = footer_text(page())
        self.assertIn("Point de départ : Le Quotidien du Pharmacien (titre et résumé).", t)
        self.assertIn(PRESS_SENTENCE.format(src="Le Quotidien du Pharmacien") + " " + TAIL, t)
        self.assertIn(EDITOR, t)
        self.assertIn(REPORT, t)
        self.assertIn("Découvrir les formations Pharm'Alpha", t)

    def test_press_source_is_a_link_and_url_is_escaped(self):
        p = page()
        self.assertIn('<a href="https://www.exemple.fr/article?a=1&amp;b=2" rel="nofollow noopener">Le Quotidien du Pharmacien</a>', p)
        self.assertIn('href="https://pharmalpha.fr/mentions-legales"', p)
        self.assertIn('href="https://pharmalpha.fr/formations"', p)

    def test_no_dead_link_when_the_source_has_no_url(self):
        p = page(source_url="")
        self.assertNotIn('href="#"', p)
        self.assertIn("Point de départ : Le Quotidien du Pharmacien (titre et résumé).", footer_text(p))
        self.assertNotIn("isBasedOn", jsonld(p))

    def test_plain_names_are_kept_whole_commas_included(self):
        self.assertEqual(ua._ai_source_label("De Hogeweyk, site officiel"), "De Hogeweyk, site officiel")
        self.assertEqual(ua._ai_source_label("Le Quotidien du Pharmacien"), "Le Quotidien du Pharmacien")
        self.assertEqual(ua._ai_source_label(""), "")

    def test_official_text_first_in_a_composite_source_gives_the_media_after_the_dash(self):
        src = "Pharm'Actus · Décret n° 2026-832 du 29 août 2026 " + EM + " Légifrance, IQVIA Pharmastat"
        self.assertEqual(ua._ai_source_label(src), "Légifrance")

    def test_long_labels_are_cut_on_a_word(self):
        self.assertLessEqual(len(ua._ai_source_label("Pharm'Actus · " + "mot " * 40)), 90)
        self.assertFalse(ua._ai_source_label("Pharm'Actus · " + "mot " * 40).endswith("mo"))


class Selection(unittest.TestCase):
    """Ordre de l'avis (8.2) : 1 LSV, 2 Business, 3 media nomme hors Pharm'Alpha et Pharm'Actus, 4 generique."""

    def test_pharm_alpha_and_pharm_actus_are_never_a_press_media(self):
        for name in ("Pharm'Alpha", "Pharm'Actus", "pharm'alpha", "Pharm" + chr(0x2019) + "Alpha", "Pharm'Actus "):
            self.assertEqual(ua._ai_source_label(name), "", name)

    def test_default_source_of_hand_injected_content_is_never_announced_as_a_starting_point(self):
        for cat in ("pharma_france", "sante", "bonne_nouvelle", ""):
            t = footer_text(page(categorie=cat, source="Pharm'Alpha", source_url="https://pharmalpha.fr"))
            self.assertNotIn("Point de départ", t)
            self.assertNotIn("titre et du résumé", t)
            self.assertIn(GENERIC_SENTENCE + " " + TAIL, t)

    def test_everything_else_gets_the_generic_variant_verbatim(self):
        for kw in (dict(source="Pharm'Actus", source_url=""), dict(source="", source_url=""), dict(source="Pharm'Alpha")):
            p = page(**kw)
            t = footer_text(p)
            self.assertIn(GENERIC_SENTENCE + " " + TAIL, t)
            self.assertNotIn("Point de départ", t)
            self.assertNotIn("faits historiques", t)
            self.assertEqual(jsonld(p)["creditText"], CREDIT["generic"])
            self.assertNotIn("isBasedOn", jsonld(p))

    def test_lsv_is_recognised_by_category_or_by_identifier(self):
        for p in (lsv(), page("lsv_2026_10_03", "", "Pharm'Alpha", ""), page("lsv_2026_10_04", "business_officine", COMPOSITE, MONDE_URL)):
            t = footer_text(p)
            self.assertIn(LSV_SENTENCE + " " + TAIL, t)
            self.assertNotIn("Point de départ", t)
            self.assertNotIn("Première source", t)
            self.assertEqual(jsonld(p)["creditText"], CREDIT["lsv"])
        self.assertIn(LSV_SENTENCE, footer_text(page("x_1", "lsv", "Le Monde", "https://www.lemonde.fr/x")))

    def test_lsv_never_says_single_press_source_and_says_none(self):
        t = footer_text(lsv())
        self.assertNotIn("source de presse unique", t)
        self.assertIn("sans source de presse, puis publié automatiquement", t)


class BusinessVariant(unittest.TestCase):
    def test_business_with_media_and_url_is_verbatim(self):
        t = footer_text(business())
        self.assertIn(BUSINESS_FIRST_SOURCE.format(src="Le Monde Santé"), t)
        self.assertIn(BUSINESS_PARAGRAPH, t)
        self.assertIn(EDITOR, t)
        self.assertIn(REPORT, t)
        self.assertIn("Découvrir les formations Pharm'Alpha", t)
        self.assertLess(t.index("Première source"), t.index(BUSINESS_PARAGRAPH))
        self.assertLess(t.index(BUSINESS_PARAGRAPH), t.index("Éditeur et directeur de la publication"))

    def test_business_never_claims_a_provenance_the_pipeline_cannot_establish(self):
        for p in (business(), business("Pharm'Actus", ""), business("Le Quotidien du Pharmacien", "https://www.exemple.fr/a"),
                  business("Pharm'Alpha", "")):
            t = footer_text(p)
            self.assertNotIn("à partir du titre et du résumé", t)
            self.assertNotIn("Point de départ", t)
            self.assertNotIn("Ce texte a été généré", t)
            self.assertIn(BUSINESS_PARAGRAPH, t)

    def test_first_source_line_needs_a_media_and_a_url(self):
        self.assertIn("Première source", footer_text(business()))
        self.assertNotIn("Première source", footer_text(business(COMPOSITE, "")))
        self.assertNotIn("Première source", footer_text(business("Pharm'Actus", "")))
        self.assertNotIn("Première source", footer_text(business("Pharm'Actus", MONDE_URL)))
        self.assertNotIn("Première source", footer_text(business("Pharm'Alpha", MONDE_URL)))
        self.assertNotIn("Première source", footer_text(business("", "")))

    def test_first_source_is_a_nofollow_link_to_the_first_media_only(self):
        p = business()
        self.assertIn('<strong>Première source indiquée par l\'intelligence artificielle :</strong> '
                      '<a href="https://www.lemonde.fr/x" rel="nofollow noopener">Le Monde Santé</a>.</p>', p)
        self.assertNotIn("Légifrance", footer_text(p))
        self.assertNotIn("Pharm'Actus ·", footer_text(p))

    def test_selector_is_the_category_not_the_presence_of_a_media(self):
        plain = business("Le Quotidien du Pharmacien", "https://www.exemple.fr/a")
        self.assertIn(BUSINESS_PARAGRAPH, footer_text(plain))
        self.assertIn("Première source indiquée par l'intelligence artificielle : Le Quotidien du Pharmacien.", footer_text(plain))

    def test_credit_text_and_no_isbasedon_even_with_a_real_media(self):
        for p in (business(), business("Pharm'Actus", ""), business("Le Quotidien du Pharmacien", "https://www.exemple.fr/a")):
            ld = jsonld(p)
            self.assertEqual(ld["creditText"], CREDIT["business"])
            self.assertNotIn("isBasedOn", ld)

    def test_other_news_sections_keep_the_standard_variant(self):
        for cat in ("pharma_france", "pharma_monde", "bonne_nouvelle", "avenir_pharma"):
            p = page(categorie=cat)
            t = footer_text(p)
            self.assertIn(PRESS_SENTENCE.format(src="Le Quotidien du Pharmacien") + " " + TAIL, t)
            self.assertEqual(jsonld(p)["isBasedOn"], "https://www.exemple.fr/article?a=1&b=2")


class JsonLd(unittest.TestCase):
    def test_author_is_the_organization_and_credit_matches_the_visible_text(self):
        ld = jsonld(page())
        self.assertEqual(ld["author"], {"@type": "Organization", "name": "Pharm'Actus", "url": "https://pharmalpha.fr/actus"})
        self.assertEqual(ld["publisher"], {"@id": "https://pharmalpha.fr/#org"})
        self.assertEqual(ld["creditText"], CREDIT["press"].format(src="Le Quotidien du Pharmacien"))
        self.assertEqual(ld["isBasedOn"], "https://www.exemple.fr/article?a=1&b=2")

    def test_credit_text_table_of_the_avis(self):
        self.assertEqual(jsonld(lsv())["creditText"], CREDIT["lsv"])
        self.assertEqual(jsonld(business())["creditText"], CREDIT["business"])
        self.assertEqual(jsonld(page(source="Pharm'Actus", source_url=""))["creditText"], CREDIT["generic"])

    def test_is_based_on_exists_only_for_a_real_named_media_with_a_url(self):
        self.assertIn("isBasedOn", jsonld(page()))
        for p in (lsv(), business(), page(source="Pharm'Alpha"), page(source="Pharm'Actus"), page(source_url=""), page(source="")):
            self.assertNotIn("isBasedOn", jsonld(p))

    def test_no_person_editor_reviewedby_or_contributor_anywhere(self):
        def walk(o):
            if isinstance(o, dict):
                yield o
                for v in o.values():
                    yield from walk(v)
            elif isinstance(o, list):
                for v in o:
                    yield from walk(v)
        for p in (page(), lsv(), business(), page(source="Pharm'Actus", source_url="")):
            for node in walk(jsonld(p)):
                self.assertNotEqual(node.get("@type"), "Person")
                for key in ("editor", "reviewedBy", "contributor", "creator", "accountablePerson"):
                    self.assertNotIn(key, node)

    def test_nothing_announces_an_editorial_policy_or_a_parent_entity_that_does_not_exist(self):
        for p in (page(), lsv(), business(), page(source="Pharm'Actus", source_url="")):
            ld = json.dumps(jsonld(p))
            for key in FORBIDDEN_JSONLD:
                self.assertNotIn(key, ld, key)

    def test_date_modified_follows_the_article_and_is_not_touched_by_the_attribution(self):
        self.assertEqual(jsonld(page())["dateModified"], "2026-10-02T06:00:00+02:00")
        self.assertEqual(jsonld(page(date_modified="2026-09-01"))["dateModified"], "2026-09-01T06:00:00+02:00")
        self.assertEqual(jsonld(page(date_modified="2026-09-01"))["datePublished"], "2026-10-02T06:00:00+02:00")


class NoSignature(unittest.TestCase):
    def test_nothing_signs_the_page_with_a_person(self):
        for p in (page(), lsv(), business(), business("Pharm'Actus", ""), page(source="Pharm'Actus", source_url="")):
            for bad in FORBIDDEN:
                self.assertNotIn(bad, p.replace("stephen@pharmalpha.fr", ""), bad)

    def test_template_adds_no_long_or_short_dash(self):
        for p in (page(), lsv(), business(), business("Pharm'Actus", "")):
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
