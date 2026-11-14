import unittest

from mkvsd.models import Category as C
from tests.helpers import mk


class ClassifierTests(unittest.TestCase):
    def test_latino_names(self):
        for name in ["ESP LAT", "ESP-LAT", "ESP_LAT", "Español Latino", "Spanish Latino", "Latino",
                     "Latin American Spanish", "Spanish (Latin America)", "LATAM", "Español (México)"]:
            with self.subTest(name=name):
                self.assertEqual(mk(1, name).category, C.LATINO)

    def test_castellano_explicit(self):
        for name in ["Castellano", "ESP CAST", "ESP-CAST", "Spanish (Spain)", "European Spanish",
                     "es-ES", "Español (España)"]:
            with self.subTest(name=name):
                self.assertEqual(mk(1, name, language="und").category, C.CASTELLANO)

    def test_generic_defaults_to_castellano_group(self):
        for name in ["ESP", "Español", "Spanish", "Espanol"]:
            with self.subTest(name=name):
                self.assertEqual(mk(1, name, language="und").category, C.GENERICO)

    def test_other_languages(self):
        self.assertEqual(mk(1, "English", "eng").category, C.OTRO)
        self.assertEqual(mk(1, "English Commentary", "eng").category, C.OTRO)
        self.assertEqual(mk(1, "", "eng").category, C.OTRO)
        self.assertEqual(mk(1, "Català", "cat").category, C.OTRO)

    def test_latin_language_is_not_latino(self):
        self.assertEqual(mk(1, "Latin", "lat").category, C.OTRO)
        self.assertEqual(mk(1, "", "lat").category, C.OTRO)
        self.assertEqual(mk(1, "ESP LAT", "lat").category, C.LATINO)

    def test_ietf_when_name_is_silent(self):
        self.assertEqual(mk(1, "", "spa", "es-419").category, C.LATINO)
        self.assertEqual(mk(1, "", "spa", "es-MX").category, C.LATINO)
        self.assertEqual(mk(1, "", "spa", "es-ES").category, C.CASTELLANO)
        self.assertEqual(mk(1, "", "spa", "es").category, C.GENERICO)
        self.assertEqual(mk(1, "", "spa", "").category, C.GENERICO)

    def test_name_beats_ietf(self):
        self.assertEqual(mk(1, "Castellano", "spa", "es-MX").category, C.CASTELLANO)
        self.assertEqual(mk(1, "ESP LAT", "spa", "es-ES").category, C.LATINO)
        # Genérico + indicio latino en IETF => latino
        self.assertEqual(mk(1, "ESP", "spa", "es-419").category, C.LATINO)

    def test_ambiguous(self):
        self.assertEqual(mk(1, "Español Latino/Castellano").category, C.AMBIGUO)
        self.assertEqual(mk(1, "English", "spa").category, C.AMBIGUO)

    def test_flags(self):
        self.assertTrue(mk(1, "ESP Forzados").is_forced)
        self.assertTrue(mk(1, "ESP", forced=True).is_forced)
        self.assertTrue(mk(1, "Spanish Commentary").is_commentary)
        self.assertTrue(mk(1, "ESP SDH").is_sdh)
        self.assertFalse(mk(1, "ESP").is_forced)


if __name__ == "__main__":
    unittest.main()
