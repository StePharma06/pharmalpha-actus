"""
Tests des mentions de transparence IA de la newsletter LinkedIn (AI Act art. 50, bloc E de l'avis d'Emilie du
2026-10-02 corrige en section 8.3), a reproduire MOT POUR MOT : si un test casse parce qu'on a reformule un texte,
c'est voulu, il faut son accord.

Il y a DEUX mentions : une en tete du corps (sous le titre), une en fin. Elles sont imposees par le code
(_enforce_ai_notice), pas par le prompt : ces tests simulent un modele qui les oublie, les reformule, les duplique
ou tronque sa sortie. Ni "automatiquement" ni "sans relecture" : Stephen lit le brouillon et le publie lui-meme.
Aucun reseau, aucun fichier du depot ecrit (l'API Claude et Brevo sont remplacees par des doublures).

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

HEAD = "Texte généré par une intelligence artificielle à partir de flux de presse (titres et résumés)."
NOTICE = ("Cette newsletter est générée par une intelligence artificielle à partir de flux de presse "
          "(titres et résumés). Éditeur : Stephen Robert, Docteur en Pharmacie. "
          "Une erreur ? Écrivez à stephen@pharmalpha.fr.")
OLD_MENTION = ("Pharm'Actus est produit quotidiennement avec l'assistance d'outils d'intelligence artificielle, "
               "sous la responsabilité éditoriale de Stephen Robert, Docteur en Pharmacie. Une erreur ou une "
               "imprécision vous saute aux yeux ? Signalez-la à stephen@pharmalpha.fr, elle sera corrigée.")
FIRST_ATTEMPT = ("Cette newsletter est générée par une intelligence artificielle à partir de flux de presse (titres et résumés) "
                 "et publiée automatiquement. Éditeur : Stephen Robert, Docteur en Pharmacie. Une erreur ? Écrivez à stephen@pharmalpha.fr.")
PARAPHRASE = ("Newsletter rédigée avec l'aide d'une intelligence artificielle. Une question ? "
              "Contactez stephen@pharmalpha.fr.")
HEAD_PARAPHRASE = "Ce texte vient d'une intelligence artificielle qui lit des flux de presse."
EM, EN = chr(0x2014), chr(0x2013)

ACTUS = [{"id": "actu_2026_10_01_1", "date": "2026-10-01", "titre": "Titre un", "resume": "Résumé un.",
          "badge_label": "Pharma France", "full_text": "Texte un.", "source": "Le Quotidien du Pharmacien",
          "source_url": "https://www.exemple.fr/un"}]
LSV = {"id": "lsv_2026_10_01", "titre": "Le saviez-vous ? Un fait", "resume": "Résumé.", "full_text": "Texte."}


def model_output(last_paragraph=OLD_MENTION, first_paragraph=None, outer_fence=False, truncate_in_bloc8=False, hashtags=True, hook="Accroche.", middle=()):
    """Sortie typique du modele, sur le gabarit du prompt (titres deja passes par _strip_emdash)."""
    intro = ([first_paragraph, ""] if first_paragraph else []) + [hook, "", "Voici l'essentiel."]
    rows = [
        '# Newsletter LinkedIn "Pharm\'Actus" - Semaine S41', "",
        "## TITRE LinkedIn (titre EXACT ci-dessous, ne pas modifier)", "", "```", "Pharm'Actus - Actus du 29 septembre au 5 octobre 2026", "```", "",
        "## SOUS-TITRE", "", "```", "Deux chiffres - 7 jours, 6 actus a retenir.", "```", "",
        "## CORPS A COPIER DANS L'EDITEUR LINKEDIN", "",
        "### Bloc 1 - Intro", "", "```", *intro, "```", "",
        "### Image 01", "", "### Bloc 2 - Actu 1", "", "```", "1. Titre un", "", "Texte un.", *middle, "", "Lire sur Pharm'Actus : https://pharmalpha.fr/actus/articles/actu_2026_10_01_1.html", "", "Source : Le Quotidien du Pharmacien", "```", "",
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


def paragraphs(md):
    return [p.strip() for p in corps(md).split("\n\n") if p.strip()]


class Constants(unittest.TestCase):
    def test_texts_are_verbatim(self):
        self.assertEqual(gln.AI_NOTICE_HEAD, HEAD)
        self.assertEqual(gln.AI_NOTICE, NOTICE)

    def test_neither_says_automatic_nor_without_review_because_stephen_reads_and_publishes_the_draft(self):
        for text in (gln.AI_NOTICE_HEAD, gln.AI_NOTICE):
            for forbidden in ("automatiquement", "sans relecture", "relue", "relu ", "vérifié", "validé", "rédigé"):
                self.assertNotIn(forbidden, text)

    def test_no_long_dash_and_untouched_by_dash_stripping(self):
        for text in (gln.AI_NOTICE_HEAD, gln.AI_NOTICE):
            self.assertNotIn(EM, text)
            self.assertNotIn(EN, text)
            self.assertEqual(gln._strip_emdash(text), text)

    def test_the_end_notice_names_the_editor_as_docteur_en_pharmacie_and_gives_the_address_in_clear(self):
        self.assertIn("Éditeur : Stephen Robert, Docteur en Pharmacie.", gln.AI_NOTICE)
        self.assertIn("stephen@pharmalpha.fr", gln.AI_NOTICE)
        self.assertNotIn("responsabilité éditoriale", gln.AI_NOTICE)

    def test_the_head_notice_does_not_contain_the_end_notice_so_that_counts_stay_exact(self):
        self.assertNotIn(HEAD, NOTICE)
        self.assertNotIn(NOTICE, HEAD)


class Enforcement(unittest.TestCase):
    def check(self, md):
        out = gln._enforce_ai_notice(md)
        self.assertEqual(out.count(NOTICE), 1)
        self.assertEqual(out.count(HEAD), 1)
        ps = paragraphs(out)
        self.assertEqual(ps[0], HEAD, "la mention de tete doit ouvrir le corps")
        self.assertTrue(corps(out).rstrip().endswith(NOTICE), "la mention de fin doit terminer le corps")
        return out

    def test_adds_both_when_the_model_wrote_neither_and_replaces_the_old_mention(self):
        out = self.check(model_output(OLD_MENTION))
        for old in ("responsabilité éditoriale", "assistance d'outils", "elle sera corrigée"):
            self.assertNotIn(old, out)

    def test_the_hook_stays_right_under_the_head_notice(self):
        out = self.check(model_output(OLD_MENTION, hook="Un hook qui parle d'intelligence artificielle en pharmacie."))
        ps = paragraphs(out)
        self.assertEqual(ps[1], "Un hook qui parle d'intelligence artificielle en pharmacie.")

    def test_replaces_a_paraphrased_end_mention(self):
        out = self.check(model_output(PARAPHRASE))
        self.assertNotIn("Newsletter rédigée avec l'aide", out)

    def test_replaces_the_first_attempt_wording_that_said_published_automatically(self):
        out = self.check(model_output(FIRST_ATTEMPT))
        self.assertNotIn("publiée automatiquement", out)

    def test_replaces_a_paraphrased_head_mention(self):
        out = self.check(model_output(NOTICE, first_paragraph=HEAD_PARAPHRASE))
        self.assertNotIn(HEAD_PARAPHRASE, out)

    def test_replaces_a_head_mention_written_with_the_end_wording(self):
        self.check(model_output(NOTICE, first_paragraph=NOTICE))

    def test_adds_the_end_mention_when_the_model_forgot_it(self):
        out = self.check(model_output(last_paragraph=""))
        self.assertIn("Réponds en commentaire, je lis tout.", corps(out))

    def test_keeps_both_correct_mentions_and_is_idempotent(self):
        once = self.check(model_output(NOTICE, first_paragraph=HEAD))
        self.assertEqual(gln._enforce_ai_notice(once), once)

    def test_removes_copies_written_elsewhere(self):
        out = self.check(model_output(OLD_MENTION, hook=NOTICE))
        self.assertEqual(corps(out).count(NOTICE), 1)
        out = self.check(model_output(OLD_MENTION, hook="Hook. " + HEAD))
        self.assertEqual(corps(out).count(HEAD), 1)
        self.assertIn("Hook.", out, "le texte voisin d'une copie en ligne doit etre preserve")

    def test_removes_whole_line_copies_in_the_middle_of_the_body_and_keeps_the_text_around(self):
        out = self.check(model_output(OLD_MENTION, middle=("", NOTICE, "", HEAD, "Une phrase voisine.")))
        self.assertEqual((corps(out).count(HEAD), corps(out).count(NOTICE)), (1, 1))
        self.assertIn("Texte un.", out)
        self.assertIn("Une phrase voisine.", out)

    def test_removes_inline_copies_in_the_middle_and_keeps_the_text_around(self):
        out = self.check(model_output(OLD_MENTION, middle=("Avant. " + NOTICE + " Apres. " + HEAD + " Fin.",)))
        self.assertEqual((corps(out).count(HEAD), corps(out).count(NOTICE)), (1, 1))
        self.assertIn("Avant.", out)
        self.assertIn("Apres.", out)
        self.assertIn("Fin.", out)

    def test_outer_markdown_fence(self):
        out = self.check(model_output(OLD_MENTION, outer_fence=True))
        self.assertTrue(out.startswith("```markdown"))

    def test_truncated_output_still_carries_both_mentions(self):
        out = gln._enforce_ai_notice(model_output(OLD_MENTION, truncate_in_bloc8=True))
        self.assertEqual(out.count(NOTICE), 1)
        self.assertEqual(out.count(HEAD), 1)
        self.assertTrue(out.rstrip().endswith(NOTICE))

    def test_unexpected_structure_still_carries_both_mentions(self):
        out = gln._enforce_ai_notice("Un texte libre sans aucun bloc.\n\nDeuxième paragraphe.")
        self.assertEqual(out.count(NOTICE), 1)
        self.assertEqual(out.count(HEAD), 1)
        self.assertTrue(out.startswith(HEAD))
        self.assertTrue(out.rstrip().endswith(NOTICE))

    def test_empty_output_still_carries_both_mentions(self):
        out = gln._enforce_ai_notice("")
        self.assertEqual((out.count(HEAD), out.count(NOTICE)), (1, 1))

    def test_a_single_block_gets_both_mentions_in_the_same_fence(self):
        md = "## CORPS\n\n### Bloc 1 - Intro\n\n```\nAccroche.\n```\n"
        out = gln._enforce_ai_notice(md)
        self.assertEqual((out.count(HEAD), out.count(NOTICE)), (1, 1))
        self.assertLess(out.index(HEAD), out.index("Accroche."))
        self.assertLess(out.index("Accroche."), out.index(NOTICE))

    def test_hashtags_section_is_untouched_and_comes_after(self):
        out = self.check(model_output(OLD_MENTION))
        self.assertLess(out.index(NOTICE), out.index("#pharmacie #officine #pharmaactu"))
        self.assertEqual(gln._extract_newsletter_parts(out)["hashtags"], "#pharmacie #officine #pharmaactu")

    def test_other_blocks_are_untouched(self):
        out = gln._enforce_ai_notice(model_output(OLD_MENTION))
        for needle in ("1. Titre un", "Lire sur Pharm'Actus : https://pharmalpha.fr/actus/articles/actu_2026_10_01_1.html",
                       "Source : Le Quotidien du Pharmacien", "Ce qu'il faut retenir de la semaine :", "Voici l'essentiel."):
            self.assertIn(needle, out)

    def test_fails_closed_if_either_guarantee_cannot_be_kept(self):
        for body in ("sans mention", HEAD + "\n\nsans la mention de fin", NOTICE + "\n\nsans la mention de tete", NOTICE + "\n\n" + HEAD):
            with mock.patch.object(gln, "_extract_newsletter_parts", return_value={"titre": "t", "soustitre": "", "corps": body, "hashtags": ""}):
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

    def test_prompt_carries_both_exact_mentions_once_and_not_the_old_one(self):
        _, prompt = self.generate(model_output(NOTICE, first_paragraph=HEAD))
        self.assertEqual(prompt.count(NOTICE), 1)
        self.assertEqual(prompt.count(HEAD), 1)
        for old in ("responsabilité éditoriale", "assistance d'outils", "responsabilite editoriale", "elle sera corrigée", "publiée automatiquement"):
            self.assertNotIn(old, prompt)

    def test_prompt_forbids_inventing_an_officine_experience_and_does_not_say_pharmacien_alone(self):
        _, prompt = self.generate(model_output(NOTICE, first_paragraph=HEAD))
        self.assertIn('N\'ecris jamais "en tant que pharmacien" (son titre est Docteur en Pharmacie), n\'invente aucune experience d\'officine '
                      "ni anecdote vecue : Stephen n'exerce pas en officine.", prompt)
        self.assertIn("Tu es Stephen ROBERT, Docteur en Pharmacie et consultant", prompt)
        self.assertNotIn("pharmacien consultant", prompt)
        self.assertNotIn("24K", prompt)

    def test_output_has_both_exact_mentions_even_if_the_model_ignores_the_prompt(self):
        md, _ = self.generate(model_output(OLD_MENTION))
        self.assertEqual((md.count(HEAD), md.count(NOTICE)), (1, 1))
        self.assertNotIn("responsabilité éditoriale", md)

    def test_dash_stripping_still_applies_and_does_not_alter_the_mentions(self):
        raw = model_output(OLD_MENTION, hook="Un point " + EM + " un autre " + EN + " fin.")
        md, _ = self.generate(raw)
        self.assertNotIn(EM, md)
        self.assertNotIn(EN, md)
        self.assertEqual((md.count(HEAD), md.count(NOTICE)), (1, 1))

    def test_a_model_truncated_before_bloc_8_is_still_marked(self):
        md, _ = self.generate(model_output(OLD_MENTION, truncate_in_bloc8=True))
        self.assertEqual((md.count(HEAD), md.count(NOTICE)), (1, 1))

    def test_the_other_linkedin_prompts_carry_the_same_voice_rule(self):
        import inspect
        sentence = "n'invente aucune experience d'officine ni anecdote vecue : Stephen n'exerce pas en officine."
        companion = inspect.getsource(gln.generate_companion_post)
        self.assertIn(sentence, companion)
        self.assertIn("Tu es Stephen ROBERT, Docteur en Pharmacie et consultant", companion)
        self.assertNotIn("pharmacien consultant", companion)
        self.assertNotIn("24K", companion)
        weekly = (Path(__file__).resolve().parent / "generate_linkedin_weekly.py").read_text(encoding="utf-8")
        self.assertIn(sentence, weekly)
        self.assertNotIn("pharmacien consultant", weekly)
        self.assertNotIn("24K", weekly)


class Email(unittest.TestCase):
    def test_the_draft_email_shows_both_mentions_in_the_paste_ready_box(self):
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
        self.assertEqual(html.count(HEAD), 2)
        self.assertLess(html.index(HEAD), html.index("Accroche."))
        self.assertLess(html.index(NOTICE), html.index("Procédure (rappel)"))
        self.assertNotIn("responsabilité éditoriale", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
