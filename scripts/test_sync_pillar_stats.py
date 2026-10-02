"""
Tests des motifs et des garde-fous de sync_pillar_stats.py.
Aucun reseau, aucun fichier du depot : phrases d'essai et fichier temporaire.

Lancer : python scripts/test_sync_pillar_stats.py
(pas de `unittest discover` : test_image_quality.py, dans le meme dossier,
importe anthropic et feedparser)

Les caracteres invisibles (espaces insecables, fines, apostrophe typographique)
sont ecrits en echappements, jamais en caractere brut. Les cas sont les memes
que dans pharmalpha-site/scripts/sync-public-stats.test.mjs.
"""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_pillar_stats as sps  # noqa: E402


def numbers(text):
    return [m.group(1) for m in sps.STAT_RE.finditer(text)]


STANDALONE = [
    ("203 officines", ["203"]),
    ("203+ officines accompagnees", ["203"]),
    ("plus de 150 pharmacies d'officine", ["150"]),
    ("Et 203 pharmacies accompagnees en France", ["203"]),
    ("1000+ officines", ["1000"]),
    ("en 2026, 203 officines", ["203"]),
    ("en 2026. 203 officines", ["203"]),
    ("(203 officines)", ["203"]),
    ("<strong>203+ officines</strong>", ["203"]),
    ("203\nofficines", ["203"]),
    ("203\u00a0officines", ["203"]),
    ("203\u202fofficines", ["203"]),
    ("189 officines et 250 pharmacies", ["189", "250"]),
]

THOUSAND_SEPARATORS = [
    (" ", "espace normale"),
    ("\u00a0", "espace insecable U+00A0"),
    ("\u202f", "espace fine insecable U+202F"),
    ("\u2009", "espace fine U+2009"),
    ("\u2007", "espace de chiffre U+2007"),
    (".", "point"),
    (",", "virgule"),
    ("'", "apostrophe droite"),
    ("\u2019", "apostrophe typographique"),
    ("&nbsp;", "entite nbsp"),
    ("&#160;", "entite decimale 160"),
    ("&#xA0;", "entite hexadecimale A0 majuscule"),
    ("&#xa0;", "entite hexadecimale a0 minuscule"),
    ("&#8239;", "entite decimale 8239"),
    ("&#x202F;", "entite hexadecimale 202F majuscule"),
    ("&#x202f;", "entite hexadecimale 202f minuscule"),
    ("&thinsp;", "entite thinsp"),
    ("&#8201;", "entite decimale 8201"),
    ("&#x2009;", "entite hexadecimale 2009"),
]

NOT_STATS = [
    "9 pharmacies sur 10",
    "150 pharmacies sur 200",
    "203 officines sur 21 000",
    "12 officines",
    "99 pharmacies",
    "20502 officines",
    "12345 pharmacies",
    "203 pharmacie",
    "203 pharmaciennes",
    "203 pharmaciens",
    "203 officinales",
    "203 officinesX",
    "203 Officines",
    "2 000+ inscrits en 4 heures",
]


class StandaloneNumbers(unittest.TestCase):
    def test_standalone_numbers_are_seen(self):
        for text, expected in STANDALONE:
            with self.subTest(text=text):
                self.assertEqual(numbers(text), expected)

    def test_thousands_are_ignored_whatever_the_separator(self):
        for sep, name in THOUSAND_SEPARATORS:
            for unit in ("officines", "pharmacies"):
                with self.subTest(separator=name, unit=unit):
                    self.assertEqual(numbers(f"un panel de 1{sep}905 {unit}"), [])
                    self.assertEqual(numbers(f"En France, 20{sep}502 {unit} en 2026"), [])
                    self.assertEqual(numbers(f"1{sep}000{sep}000 {unit}"), [])

    def test_a_thousand_does_not_hide_a_real_neighbour(self):
        text = "Le panel couvre 1 905 officines et Pharm'Alpha en accompagne 203+ officines."
        self.assertEqual(numbers(text), ["203"])

    def test_not_stats(self):
        for text in NOT_STATS:
            with self.subTest(text=text):
                self.assertEqual(numbers(text), [])


FIVE = (
    "<meta name=\"description\" content=\"Guide 2026, 203+ officines accompagnees\">\n"
    "<p>Pharm'Alpha accompagne 203+ officines.</p>\n"
    "<p>Le panel couvre 1 905 officines (9 pharmacies sur 10 du reseau), sur 20\u00a0502 officines en France.</p>\n"
    "<p>Soit 203 pharmacies suivies, dont 203+ officines en conseil et 203 pharmacies en formation.</p>\n"
)


class MainGuards(unittest.TestCase):
    def run_main(self, content, pharmacies=203, fetch_error=None):
        with tempfile.TemporaryDirectory() as tmp:
            pillar = Path(tmp) / "pillar.html"
            pillar.write_text(content, encoding="utf-8")
            fetch = mock.patch.object(
                sps,
                "fetch_pharmacies_count",
                return_value=pharmacies,
                side_effect=fetch_error,
            )
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(sps, "PILLAR", pillar), fetch, \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = sps.main()
            return code, out.getvalue(), err.getvalue(), pillar.read_text(encoding="utf-8")

    def test_fixture_has_exactly_five_standalone_numbers(self):
        self.assertEqual(numbers(FIVE), ["203"] * 5)

    def test_up_to_date_writes_nothing(self):
        code, out, _err, after = self.run_main(FIVE)
        self.assertEqual(code, 0)
        self.assertIn("deja a jour (203)", out)
        self.assertEqual(after, FIVE)

    def test_update_rewrites_only_standalone_numbers(self):
        code, out, _err, after = self.run_main(FIVE, pharmacies=210)
        self.assertEqual(code, 0)
        self.assertIn("203 -> 210", out)
        expected = FIVE.replace("203+ officines", "210+ officines").replace("203 pharmacies", "210 pharmacies")
        self.assertEqual(after, expected)
        self.assertIn("1 905 officines", after)
        self.assertIn("20\u00a0502 officines", after)
        self.assertIn("9 pharmacies sur 10", after)

    def test_source_unavailable_is_a_clean_exit(self):
        code, out, _err, after = self.run_main(FIVE, fetch_error=OSError("reseau coupe"))
        self.assertEqual(code, 0)
        self.assertIn("source indisponible", out)
        self.assertEqual(after, FIVE)

    def test_unexpected_count_fails_and_names_the_excerpts(self):
        content = FIVE + "<p>Et encore 203 officines.</p>\n"
        code, _out, err, after = self.run_main(content, pharmacies=210)
        self.assertEqual(code, 1)
        self.assertIn("6 occurrence(s) trouvee(s)", err)
        self.assertIn("5 attendue(s)", err)
        self.assertIn("Vues : ", err)
        self.assertIn("Et encore 203 officines", err)
        self.assertEqual(after, content)

    def test_failure_excerpt_makes_non_breaking_spaces_visible(self):
        content = FIVE + "<p>Et encore 203\u00a0officines.</p>\n"
        _code, _out, err, _after = self.run_main(content, pharmacies=210)
        self.assertIn("203\\u00a0officines", err)

    def test_incoherent_values_fail(self):
        content = FIVE.replace("<p>Pharm'Alpha accompagne 203+ officines.</p>", "<p>Pharm'Alpha accompagne 150+ officines.</p>")
        code, _out, err, after = self.run_main(content, pharmacies=210)
        self.assertEqual(code, 1)
        self.assertIn("valeurs incoherentes", err)
        self.assertEqual(after, content)

    def test_drop_of_more_than_ten_percent_fails(self):
        code, _out, err, after = self.run_main(FIVE, pharmacies=150)
        self.assertEqual(code, 1)
        self.assertIn("chute de 203 a 150", err)
        self.assertEqual(after, FIVE)

    # Formes que le motif ne peut pas distinguer d'un vrai chiffre : elles ne
    # corrompent jamais, le compte attendu ou la coherence fait echouer le job.
    def test_known_limit_range_upper_bound_fails_closed(self):
        content = FIVE.replace(
            "<p>Pharm'Alpha accompagne 203+ officines.</p>",
            "<p>Sur des zones de 300 \u00e0 400 officines.</p>",
        )
        self.assertEqual(numbers(content).count("400"), 1)
        code, _out, err, after = self.run_main(content, pharmacies=210)
        self.assertEqual(code, 1)
        self.assertIn("valeurs incoherentes", err)
        self.assertEqual(after, content)

    def test_known_limit_sample_base_without_separator_fails_closed(self):
        content = FIVE.replace("<p>Soit 203 pharmacies suivies, dont 203+ officines en conseil et 203 pharmacies en formation.</p>",
                               "<p>Soit 203 pharmacies suivies, dont 203+ officines en conseil. L'etude porte sur 2700 officines.</p>")
        self.assertEqual(numbers(content).count("2700"), 1)
        code, _out, err, after = self.run_main(content, pharmacies=210)
        self.assertEqual(code, 1)
        self.assertIn("valeurs incoherentes", err)
        self.assertEqual(after, content)

    def test_known_limit_number_glued_to_a_year_is_not_seen(self):
        self.assertEqual(numbers("En 2025 203 officines accompagnees, puis 203 pharmacies."), ["203"])


if __name__ == "__main__":
    unittest.main()
