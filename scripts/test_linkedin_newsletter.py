"""
Tests de la mention de transparence IA de la newsletter LinkedIn (AI Act art. 50, bloc E de l'avis
d'Emilie du 2026-10-02), a reproduire MOT POUR MOT : si un test casse parce qu'on a reformule le texte,
c'est voulu, il faut son accord.

La mention est imposee par le code (_enforce_ai_notice), pas par le prompt : ces tests simulent un modele
qui l'oublie, la reformule, la duplique ou tronque sa sortie. Aucun reseau, aucun fichier du depot ecrit
(l'API Claude et Brevo sont remplacees par des doublures).

Lancer : python scripts/test_linkedin_newsletter.py
"""

import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_linkedin_newsletter as gln  # noqa: E402

NOTICE = ("Cette newsletter est générée par une intelligence artificielle à partir de flux de presse "
          "(titres et résumés) et publiée automatiquement. Éditeur : Stephen Robert, Docteur en Pharmacie. "
          "Une erreur ? Écrivez à stephen@pharmalpha.fr.")
OLD_MENTION = ("Pharm'Actus est produit quotidiennement avec l'assistance d'outils d'intelligence artificielle, "
               "sous la responsabilité éditoriale de Stephen Robert, Docteur en Pharmacie. Une erreur ou une "
               "imprécision vous saute aux yeux ? Signalez-la à stephen@pharmalpha.fr, elle sera corrigée.")
PARAPHRASE = ("Newsletter rédigée avec l'aide d'une intelligence artificielle. Une question ? "
              "Contactez stephen@pharmalpha.fr.")
EM, EN = chr(0x2014), chr(0x2013)

ACTUS = [{"id": "actu_2026_10_01_1", "date": "2026-10-01", "titre": "Titre un", "resume": "Résumé un.",
          "badge_label": "Pharma France", "full_text": "Texte un.", "source": "Le Quotidien du Pharmacien",
          "source_url": "https://www.exemple.fr/un"}]
LSV = {"id": "lsv_2026_10_01", "titre": "Le saviez-vous ? Un fait", "resume": "Résumé.", "full_text": "Texte."}


def model_output(last_paragraph=OLD_MENTION, outer_fence=False, truncate_in_bloc8=False, hashtags=True, extra_before=""):
    """Sortie typique du modele, sur le gabarit du prompt (titres deja passes par _strip_emdash)."""
    rows = [
        '# Newsletter LinkedIn "Pharm\'Actus" - Semaine S41', "",
        "## TITRE LinkedIn (titre EXACT ci-dessous, ne pas modifier)", "", "```", "Pharm'Actus - Actus du 29 septembre au 5 octobre 2026", "```", "",
        "## SOUS-TITRE", "", "```", "Deux chiffres - 7 jours, 6 actus a retenir.", "```", "",
        "## CORPS A COPIER DANS L'EDITEUR LINKEDIN", "",
        "### Bloc 1 - Intro", "", "```", "Accroche.", "", extra_before or "Voici l'essentiel.", "```", "",
        "### Image 01", "", "### Bloc 2 - Actu 1", "", "```", "1. Titre un", "", "Texte un.", "", "Lire sur Pharm'Actus : https://pharmalpha.fr/actus/articles/actu_2026_10_01_1.html", "", "Source : Le Quotidien du Pharmacien", "```", "",
        "### Image 07", "", "### Bloc 8 - Le Saviez-vous + Cloture", "", "```",
    ]
    bloc8 = ["Le Saviez-vous ? Un fait", "", "Texte du LSV.", "", "", "Ce qu'il faut retenir de la semaine :", "- Un", "- Deux", "", "",
             "Et toi, quelle actu t'a le plus interpellé cette semaine ?", "", "Réponds en commentaire, je lis tout."]
    if last_paragraph:
        bloc8 += ["", "", last_paragraph]
    rows += bloc8
    if truncate_in_bloc8:
        return "\n".join(rows)
    rows += ["```", ""]
    if hashtags:
        rows += ["## Hashtags (commentaire 1 min apres publication)", "", "```", "#pharmacie #officine #pharmaactu", "```"]
    text = "\n".join(rows)
    return "```markdown\n" + text + "\n```" if outer_fence else text


def corps(md):
    return gln._extract_newsletter_parts(md)["corps"]


class Constant(unittest.TestCase):
    def test_text_is_verbatim_bloc_e(self):
        self.assertEqual(gln.AI_NOTICE, NOTICE)

    def test_no_long_dash_and_untouched_by_dash_stripping(self):
        self.assertNotIn(EM, gln.AI_NOTICE)
        self.assertNotIn(EN, gln.AI_NOTICE)
        self.assertEqual(gln._strip_emdash(gln.AI_NOTICE), gln.AI_NOTICE)

    def test_names_the_editor_as_docteur_en_pharmacie_and_gives_the_address_in_clear(self):
        self.assertIn("Éditeur : Stephen Robert, Docteur en Pharmacie.", gln.AI_NOTICE)
        self.assertIn("stephen@pharmalpha.fr", gln.AI_NOTICE)
        self.assertNotIn("responsabilité éditoriale", gln.AI_NOTICE)


class Enforcement(unittest.TestCase):
    def check(self, md):
        out = gln._enforce_ai_notice(md)
        self.assertEqual(out.count(NOTICE), 1)
        self.assertTrue(corps(out).rstrip().endswith(NOTICE), "la mention doit terminer le corps")
        return out

    def test_replaces_the_old_mention(self):
        out = self.check(model_output(OLD_MENTION))
        self.assertNotIn("responsabilité éditoriale", out)
        self.assertNotIn("assistance d'outils", out)
        self.assertNotIn("elle sera corrigée", out)

    def test_replaces_a_paraphrase(self):
        out = self.check(model_output(PARAPHRASE))
        self.assertNotIn("Newsletter rédigée avec l'aide", out)

    def test_adds_it_when_the_model_forgot_it(self):
        out = self.check(model_output(last_paragraph=""))
        self.assertIn("Réponds en commentaire, je lis tout.", corps(out))

    def test_keeps_the_correct_mention_and_is_idempotent(self):
        once = self.check(model_output(NOTICE))
        self.assertEqual(gln._enforce_ai_notice(once), once)

    def test_keeps_a_last_paragraph_that_is_not_a_mention(self):
        out = self.check(model_output(last_paragraph=""))
        self.assertIn("Réponds en commentaire, je lis tout.", out)

    def test_removes_a_copy_written_elsewhere(self):
        out = self.check(model_output(OLD_MENTION, extra_before=NOTICE))
        self.assertEqual(corps(out).count(NOTICE), 1)

    def test_removes_an_inline_copy(self):
        out = self.check(model_output(OLD_MENTION, extra_before="Voici l'essentiel. " + NOTICE))
        self.assertIn("Voici l'essentiel.", out)

    def test_outer_markdown_fence(self):
        out = self.check(model_output(OLD_MENTION, outer_fence=True))
        self.assertTrue(out.startswith("```markdown"))

    def test_truncated_output_still_carries_the_mention(self):
        out = gln._enforce_ai_notice(model_output(OLD_MENTION, truncate_in_bloc8=True))
        self.assertEqual(out.count(NOTICE), 1)
        self.assertTrue(out.rstrip().endswith(NOTICE))

    def test_unexpected_structure_still_carries_the_mention(self):
        out = gln._enforce_ai_notice("Un texte libre sans aucun bloc.\n\nDeuxième paragraphe.")
        self.assertEqual(out.count(NOTICE), 1)
        self.assertTrue(out.rstrip().endswith(NOTICE))

    def test_empty_output_still_carries_the_mention(self):
        self.assertEqual(gln._enforce_ai_notice("").count(NOTICE), 1)

    def test_hashtags_section_is_untouched_and_comes_after(self):
        out = self.check(model_output(OLD_MENTION))
        self.assertLess(out.index(NOTICE), out.index("#pharmacie #officine #pharmaactu"))
        self.assertEqual(gln._extract_newsletter_parts(out)["hashtags"], "#pharmacie #officine #pharmaactu")

    def test_other_blocks_are_untouched(self):
        before = model_output(OLD_MENTION)
        out = gln._enforce_ai_notice(before)
        for needle in ("1. Titre un", "Lire sur Pharm'Actus : https://pharmalpha.fr/actus/articles/actu_2026_10_01_1.html",
                       "Source : Le Quotidien du Pharmacien", "Ce qu'il faut retenir de la semaine :"):
            self.assertIn(needle, out)

    def test_fails_closed_if_the_guarantee_cannot_be_kept(self):
        with mock.patch.object(gln, "_extract_newsletter_parts", return_value={"titre": "t", "soustitre": "", "corps": "sans mention", "hashtags": ""}):
            with self.assertRaises(RuntimeError):
                gln._enforce_ai_notice(model_output(OLD_MENTION))


class FullGeneration(unittest.TestCase):
    def generate(self, output):
        seen = {}

        def fake_create(client, stream=False, **kw):
            seen["prompt"] = kw["messages"][0]["content"]
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=output)])

        with mock.patch.object(gln.anthropic, "Anthropic", lambda *a, **k: object()), \
                mock.patch.object(gln, "claude_create", fake_create):
            return gln.generate_newsletter_content(ACTUS, LSV), seen["prompt"]

    def test_prompt_carries_the_exact_mention_once_and_not_the_old_one(self):
        _, prompt = self.generate(model_output(NOTICE))
        self.assertEqual(prompt.count(NOTICE), 1)
        for old in ("responsabilité éditoriale", "assistance d'outils", "responsabilite editoriale", "elle sera corrigée"):
            self.assertNotIn(old, prompt)

    def test_output_has_the_exact_mention_even_if_the_model_ignores_the_prompt(self):
        md, _ = self.generate(model_output(OLD_MENTION))
        self.assertEqual(md.count(NOTICE), 1)
        self.assertNotIn("responsabilité éditoriale", md)

    def test_dash_stripping_still_applies_and_does_not_alter_the_mention(self):
        raw = model_output(OLD_MENTION, extra_before="Un point " + EM + " un autre " + EN + " fin.")
        md, _ = self.generate(raw)
        self.assertNotIn(EM, md)
        self.assertNotIn(EN, md)
        self.assertEqual(md.count(NOTICE), 1)

    def test_a_model_truncated_before_bloc_8_is_still_marked(self):
        md, _ = self.generate(model_output(OLD_MENTION, truncate_in_bloc8=True))
        self.assertEqual(md.count(NOTICE), 1)


class Email(unittest.TestCase):
    def test_the_draft_email_shows_the_mention_in_the_paste_ready_box(self):
        md = gln._enforce_ai_notice(model_output(OLD_MENTION))
        sent = {}

        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"messageId": "test"}'

        def fake_urlopen(req, timeout=None):
            sent["payload"] = json.loads(req.data.decode("utf-8"))
            return Reply()

        with mock.patch.dict(os.environ, {"BREVO_API_KEY": "test"}), \
                mock.patch.object(gln.urllib.request, "urlopen", fake_urlopen), \
                mock.patch.object(gln, "build_email_attachments", lambda a, l: []):
            gln.send_newsletter_email(md, ACTUS, LSV, companion_post="")

        html = sent["payload"]["htmlContent"]
        self.assertEqual(html.count(NOTICE), 2, "une fois dans la version prete a coller, une fois dans le markdown brut")
        self.assertLess(html.index(NOTICE), html.index("Procédure (rappel)"))
        self.assertNotIn("responsabilité éditoriale", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
