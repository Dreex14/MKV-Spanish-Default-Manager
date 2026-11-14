import unittest

from mkvsd.models import Status as S
from mkvsd.selector import decide
from tests.helpers import mk


def result(tracks, **kw):
    d = decide(tracks, **kw)
    return d, {c.track.index: c.new_default for c in d.changes}


class SelectorTests(unittest.TestCase):
    def test_spec_example(self):
        tracks = [mk(1, "English", "eng"), mk(2, "ESP LAT", default=True),
                  mk(3, "ESP"), mk(4, "English Commentary", "eng")]
        d, ch = result(tracks)
        self.assertEqual(d.status, S.TO_CHANGE)
        self.assertEqual(d.selected.index, 3)
        self.assertEqual(ch, {2: False, 3: True})

    def test_latino_vs_castellano(self):
        d, ch = result([mk(1, "Español Latino", default=True), mk(2, "Castellano")])
        self.assertEqual((d.selected.index, ch), (2, {1: False, 2: True}))

    def test_latino_vs_spanish(self):
        d, ch = result([mk(1, "Latino", default=True), mk(2, "Spanish")])
        self.assertEqual((d.selected.index, ch), (2, {1: False, 2: True}))

    def test_explicit_castellano_beats_generic(self):
        d, _ = result([mk(1, "ESP"), mk(2, "Castellano")])
        self.assertEqual(d.selected.index, 2)

    def test_full_beats_forced_and_commentary(self):
        d, _ = result([mk(1, "Castellano Forzados"), mk(2, "Comentarios ESP"), mk(3, "ESP")])
        self.assertEqual(d.selected.index, 3)

    def test_only_latino_untouched(self):
        d, ch = result([mk(1, "English", "eng"), mk(2, "ESP LAT")])
        self.assertEqual((d.status, ch), (S.ONLY_LATINO, {}))

    def test_no_spanish(self):
        d, ch = result([mk(1, "English", "eng", default=True)])
        self.assertEqual((d.status, ch), (S.NO_SPANISH, {}))

    def test_spanish_commentary_only(self):
        d, _ = result([mk(1, "Spanish Commentary")])
        self.assertEqual(d.status, S.NO_SPANISH)

    def test_already_ok(self):
        d, ch = result([mk(1, "ESP LAT"), mk(2, "ESP", default=True)])
        self.assertEqual((d.status, ch), (S.ALREADY_OK, {}))

    def test_only_forced_castellano_goes_to_review(self):
        d, ch = result([mk(1, "ESP LAT", default=True), mk(2, "ESP Forzados")])
        self.assertEqual((d.status, ch), (S.REVIEW, {}))

    def test_ambiguous_and_nothing_else(self):
        d, _ = result([mk(1, "Español Latino/Castellano")])
        self.assertEqual(d.status, S.REVIEW)

    def test_ambiguous_with_explicit_castellano_ok(self):
        d, _ = result([mk(1, "Español Latino/Castellano"), mk(2, "Castellano")])
        self.assertEqual((d.status, d.selected.index), (S.TO_CHANGE, 2))

    def test_ambiguous_with_generic_goes_to_review(self):
        d, _ = result([mk(1, "Español Latino/Castellano"), mk(2, "ESP")])
        self.assertEqual(d.status, S.REVIEW)

    def test_tie_resolved_by_current_default(self):
        d, ch = result([mk(1, "Castellano"), mk(2, "Castellano", default=True)])
        self.assertEqual((d.status, d.selected.index), (S.ALREADY_OK, 2))

    def test_unresolved_tie_goes_to_review(self):
        d, _ = result([mk(1, "Castellano"), mk(2, "Castellano")])
        self.assertEqual(d.status, S.REVIEW)

    def test_sdh_ranks_below_normal(self):
        d, _ = result([mk(1, "ESP SDH"), mk(2, "ESP")])
        self.assertEqual(d.selected.index, 2)

    def test_duplicate_default_spanish_is_cleared(self):
        d, ch = result([mk(1, "Castellano", default=True), mk(2, "ESP", default=True)])
        self.assertEqual((d.selected.index, ch), (1, {2: False}))

    def test_forced_default_spanish_is_left_alone(self):
        d, ch = result([mk(1, "ESP Forzados", default=True), mk(2, "ESP")])
        self.assertEqual(ch, {2: True})

    def test_other_languages_untouched_by_default(self):
        tracks = [mk(1, "English", "eng", default=True), mk(2, "ESP")]
        self.assertEqual(result(tracks)[1], {2: True})
        self.assertEqual(result(tracks, clear_other_defaults=True)[1], {1: False, 2: True})

    def test_ietf_only_tracks(self):
        d, ch = result([mk(1, "", "spa", "es-419", default=True), mk(2, "", "spa", "es-ES")])
        self.assertEqual(ch, {1: False, 2: True})


if __name__ == "__main__":
    unittest.main()
