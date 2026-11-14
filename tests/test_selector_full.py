import unittest

from mkvsd.models import Status
from mkvsd.selector_full import Pick, decide_full
from tests.helpers import mk


def sel(d):
    return d.selected.index if d.selected else None


class FullSelectorTests(unittest.TestCase):
    def test_castellano_over_latino(self):
        d = decide_full([mk(1, "ESP LAT", default=True), mk(2, "ESP"), mk(3, "English", "eng")])
        self.assertEqual((d.pick, d.status, sel(d)), (Pick.CASTELLANO, Status.TO_CHANGE, 2))
        self.assertTrue(any(c.track.index == 1 and not c.new_default for c in d.changes))

    def test_castellano_already_default(self):
        d = decide_full([mk(1, "Castellano", default=True), mk(2, "ESP LAT")])
        self.assertEqual((d.pick, d.status), (Pick.CASTELLANO, Status.ALREADY_OK))

    def test_latino_when_no_castellano(self):
        d = decide_full([mk(1, "English", "eng", default=True), mk(2, "ESP LAT"), mk(3, "Spanish Latino SDH")])
        self.assertEqual((d.pick, d.status, sel(d)), (Pick.LATINO, Status.TO_CHANGE, 2))

    def test_latino_prefers_non_sdh_and_default_breaks_ties(self):
        d = decide_full([mk(1, "Latino SDH"), mk(2, "Latino")])
        self.assertEqual(sel(d), 2)
        d = decide_full([mk(1, "Latino A"), mk(2, "Latino B", default=True)])
        self.assertEqual((d.pick, d.status), (Pick.LATINO, Status.ALREADY_OK))
        d = decide_full([mk(1, "Latino A"), mk(2, "Latino B")])
        self.assertEqual(d.pick, Pick.REVIEW)

    def test_never_latino_if_castellano_exists_even_if_forced_only_castellano(self):
        d = decide_full([mk(1, "ESP LAT", default=True), mk(2, "ESP Forzados"), mk(3, "English", "eng")])
        self.assertEqual(d.pick, Pick.REVIEW)           # nunca se elige la latina
        self.assertEqual(d.changes, [])

    def test_single_other_language(self):
        d = decide_full([mk(1, "English", "eng")])
        self.assertEqual((d.pick, d.status, sel(d)), (Pick.OTHER_SINGLE, Status.TO_CHANGE, 1))
        d = decide_full([mk(1, "English", "eng", default=True)])
        self.assertEqual((d.pick, d.status), (Pick.OTHER_SINGLE, Status.ALREADY_OK))

    def test_several_other_languages_keep_original(self):
        d = decide_full([mk(1, "English", "eng", default=True), mk(2, "Français", "fre")])
        self.assertEqual((d.pick, d.status, d.changes), (Pick.KEEP, Status.NO_SPANISH, []))

    def test_no_subtitles(self):
        d = decide_full([])
        self.assertEqual((d.pick, d.changes), (Pick.NO_SUBS, []))

    def test_forced_and_commentary_do_not_count_as_candidates(self):
        d = decide_full([mk(1, "English", "eng"), mk(2, "English Forced", "eng", forced=True),
                         mk(3, "Director Commentary", "eng")])
        self.assertEqual((d.pick, sel(d)), (Pick.OTHER_SINGLE, 1))
        d = decide_full([mk(1, "English", "eng"), mk(2, "French", "fre"), mk(3, "English Forced", "eng", forced=True)])
        self.assertEqual(d.pick, Pick.KEEP)

    def test_only_track_is_forced_or_commentary_single_rule(self):
        d = decide_full([mk(1, "English Forced", "eng", forced=True)])
        self.assertEqual((d.pick, sel(d)), (Pick.OTHER_SINGLE, 1))
        d = decide_full([mk(1, "ESP Forzados", forced=True)])
        self.assertEqual((d.pick, sel(d)), (Pick.CASTELLANO, 1))
        d = decide_full([mk(1, "Latino Forzados", forced=True)])
        self.assertEqual((d.pick, sel(d)), (Pick.LATINO, 1))

    def test_forced_and_commentary_only_with_several_tracks_keep(self):
        d = decide_full([mk(1, "English Forced", "eng", forced=True), mk(2, "French Commentary", "fre")])
        self.assertEqual(d.pick, Pick.KEEP)

    def test_ambiguous_goes_to_review(self):
        d = decide_full([mk(1, "Latino/Castellano", default=True), mk(2, "English", "eng")])
        self.assertEqual(d.pick, Pick.REVIEW)

    def test_clear_other_defaults_option(self):
        tracks = [mk(1, "English", "eng", default=True), mk(2, "ESP LAT")]
        self.assertEqual([c.track.index for c in decide_full(tracks, True).changes], [2, 1])
        self.assertEqual([c.track.index for c in decide_full(tracks, False).changes], [2])

    def test_same_as_original_selector_when_castellano_exists(self):
        from mkvsd.selector import decide
        tracks = [mk(1, "ESP LAT", default=True), mk(2, "ESP"), mk(3, "English", "eng")]
        a, b = decide(tracks), decide_full([mk(1, "ESP LAT", default=True), mk(2, "ESP"), mk(3, "English", "eng")])
        self.assertEqual((a.status, a.selected.index, [(c.track.index, c.new_default) for c in a.changes]),
                         (b.status, b.selected.index, [(c.track.index, c.new_default) for c in b.changes]))


if __name__ == "__main__":
    unittest.main()
