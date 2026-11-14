import os
import tempfile
import unittest
from pathlib import Path

from mkvsd import rename_history as rh
from mkvsd.fullmode import build_full_plan, describe_entry_result, execute_full_plan
from mkvsd.mkvtools import MkvTools, MkvToolError, parse_tracks
from mkvsd.renamer import RenameRules, parse_extensions
from mkvsd.selector_full import Pick

CAST = [("English", "eng", False), ("ESP LAT", "spa", True), ("ESP", "spa", False)]
LAT = [("English", "eng", True), ("ESP LAT", "spa", False)]
ONE_ENG = [("English", "eng", False)]
MANY = [("English", "eng", True), ("French", "fre", False)]
NONE = []
REVIEW = [("ESP LAT", "spa", True), ("ESP Forzados", "spa", False), ("English", "eng", False)]


class FileKeyedFake(MkvTools):
    """El estado de pistas vive en memoria, ligado al CONTENIDO del archivo (su id), no a su nombre."""

    def __init__(self, states):
        super().__init__("mkvmerge", "mkvpropedit")
        self.states = {k: [list(t) for t in v] for k, v in states.items()}

    def _id(self, path):
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise MkvToolError(str(exc))

    def probe(self, path):
        tracks = [{"id": 0, "type": "video", "properties": {"uid": 1}}]
        for i, (name, lang, default) in enumerate(self.states[self._id(path)], 1):
            tracks.append({"id": i, "type": "subtitles", "properties": {
                "uid": 100 + i, "track_name": name, "language": lang, "default_track": default}})
        return parse_tracks({"container": {"recognized": True}, "tracks": tracks})

    def run_propedit(self, cmd):
        state = self.states[self._id(cmd[3])]
        it = iter(cmd[4:])
        for a in it:
            if a == "--edit":
                uid = int(next(it).split("=")[1])
                next(it)
                state[uid - 101][2] = next(it).endswith("=1")


class FullModeTests(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.TemporaryDirectory()
        self.work = tempfile.TemporaryDirectory()
        os.environ["MKVSD_DATA_DIR"] = self.data.name
        states = {"cast": CAST, "lat": LAT, "one": ONE_ENG, "many": MANY, "none": NONE, "review": REVIEW}
        self.tools = FileKeyedFake(states)
        names = {
            "Serie [1080p_] E01.mkv": "cast", "Serie [1080p_] E02.mkv": "lat", "Serie [1080p_] E03.mkv": "one",
            "Serie [1080p_] E04.mkv": "many", "Serie [1080p_] E05.mkv": "none", "Serie [1080p_] E06.mkv": "review",
            "Serie E07.mkv": "cast",            # ya limpio
            "Serie [1080p_] E01.srt": "texto",  # no MKV
        }
        for n, content in names.items():
            Path(self.work.name, n).write_text(content, encoding="utf-8")
        self.rules = RenameRules(removals=["[1080p_]"])
        self.exts = parse_extensions("mkv, srt")

    def tearDown(self):
        self.data.cleanup()
        self.work.cleanup()

    def plan(self, **kw):
        return build_full_plan(self.tools, self.work.name, True, kw.pop("rules", self.rules), self.exts, **kw)

    def listing(self):
        return sorted(os.listdir(self.work.name))

    def test_preview_modifies_nothing(self):
        before = self.listing()
        states_before = {k: [list(t) for t in v] for k, v in self.tools.states.items()}
        plan = self.plan()
        self.assertEqual(self.listing(), before)
        self.assertEqual(self.tools.states, states_before)
        rows = dict(plan.rows())
        self.assertEqual(rows["Archivos que se renombrarán"], 7)
        self.assertEqual(rows["Archivos sin cambios de nombre"], 1)
        self.assertEqual(rows["MKV que se modificarán"], 4)       # E01 y E07 (mismo estado "cast"), E02 y E03
        self.assertEqual(rows["Episodios con castellano seleccionado"], 2)
        self.assertEqual(rows["Episodios con latino seleccionado por ausencia de castellano"], 1)
        self.assertEqual(rows["Episodios con otro idioma seleccionado por ser la única pista"], 1)
        self.assertEqual(rows["Episodios sin subtítulos"], 1)
        self.assertEqual(rows["Archivos que necesitan revisión"], 1)

    def test_full_run_report(self):
        plan = self.plan()
        seen = []
        rep = execute_full_plan(self.tools, plan, on_result=seen.append)
        self.assertEqual(self.listing(), ["Serie E01.mkv", "Serie E01.srt", "Serie E02.mkv", "Serie E03.mkv",
                                          "Serie E04.mkv", "Serie E05.mkv", "Serie E06.mkv", "Serie E07.mkv"])
        r = dict(rep.rows())
        self.assertEqual(r["Archivos renombrados"], 7)
        self.assertEqual(r["Archivos sin cambios de nombre"], 1)
        self.assertEqual(r["MKV modificados"], 3)
        self.assertEqual(r["Episodios con castellano seleccionado"], 2)
        self.assertEqual(r["Episodios con latino seleccionado por ausencia de castellano"], 1)
        self.assertEqual(r["Episodios con otro idioma seleccionado por ser la única pista"], 1)
        self.assertEqual(r["Episodios sin español y con varios idiomas (se conserva)"], 1)
        self.assertEqual(r["Episodios sin subtítulos"], 1)
        self.assertEqual(r["Archivos que necesitan revisión"], 1)
        self.assertEqual(r["Errores"], 0)
        self.assertEqual(len(seen), 8)
        # estados reales
        self.assertEqual([t[2] for t in self.tools.states["cast"]], [False, False, True])
        self.assertEqual([t[2] for t in self.tools.states["lat"]], [True, True])  # ya lo era: latino → EN sigue default
        self.assertTrue(self.tools.states["one"][0][2])
        self.assertEqual([t[2] for t in self.tools.states["many"]], [True, False])   # sin tocar
        self.assertEqual([t[2] for t in self.tools.states["review"]], [True, False, False])  # sin tocar

    def test_rename_runs_before_subtitles_and_target_path_is_new(self):
        rep = execute_full_plan(self.tools, self.plan())
        r = next(x for x in rep.results if x.entry.path.name == "Serie [1080p_] E01.mkv")
        self.assertEqual(r.final_path.name, "Serie E01.mkv")
        self.assertEqual(r.apply.analysis.path.name, "Serie E01.mkv")
        self.assertEqual(r.apply.outcome, "ok")
        self.assertIn("renombrado → Serie E01.mkv", describe_entry_result(r))

    def test_conflict_is_not_renamed_but_subtitles_still_processed(self):
        Path(self.work.name, "Serie E01.mkv").write_text("lat", encoding="utf-8")   # ocupa el nombre limpio
        plan = self.plan()
        rep = execute_full_plan(self.tools, plan)
        self.assertIn("Serie [1080p_] E01.mkv", self.listing())               # intacto
        self.assertEqual(Path(self.work.name, "Serie E01.mkv").read_text(encoding="utf-8"), "lat")
        names = {Path(p).name for p, _ in rep.review}
        self.assertIn("Serie [1080p_] E01.mkv", names)
        self.assertEqual([t[2] for t in self.tools.states["cast"]], [False, False, True])  # subtítulos sí

    def test_undo_after_full_run_restores_names(self):
        execute_full_plan(self.tools, self.plan())
        entry = rh.last_undoable()
        self.assertEqual((entry.mode, len(entry.renames)), ("full", 7))
        self.assertEqual(rh.undo_last().reverted, 7)
        self.assertIn("Serie [1080p_] E01.mkv", self.listing())

    def test_second_run_is_idempotent(self):
        execute_full_plan(self.tools, self.plan())
        rep = execute_full_plan(self.tools, self.plan())
        r = dict(rep.rows())
        self.assertEqual((r["Archivos renombrados"], r["MKV modificados"]), (0, 0))

    def test_mkv_not_in_extension_filter_still_gets_subtitles_but_no_rename(self):
        plan = build_full_plan(self.tools, self.work.name, True, self.rules, parse_extensions("srt"))
        rep = execute_full_plan(self.tools, plan)
        self.assertEqual(rep.renamed, 1)                       # solo el .srt
        self.assertIn("Serie [1080p_] E01.mkv", self.listing())
        self.assertEqual(rep.mkv_modified, 3)

    def test_probe_error_is_reported(self):
        Path(self.work.name, "Serie roto.mkv").write_text("desconocido", encoding="utf-8")
        rep = execute_full_plan(self.tools, self.plan())
        self.assertEqual(dict(rep.rows())["Errores"], 1)

    def test_cancel(self):
        plan = self.plan()
        rep = execute_full_plan(self.tools, plan, cancelled=lambda: True)
        self.assertTrue(rep.cancelled)

    def test_non_recursive_and_subfolders(self):
        Path(self.work.name, "sub").mkdir()
        Path(self.work.name, "sub", "X [1080p_].mkv").write_text("cast", encoding="utf-8")
        flat = build_full_plan(self.tools, self.work.name, False, self.rules, self.exts)
        deep = build_full_plan(self.tools, self.work.name, True, self.rules, self.exts)
        self.assertEqual(len(deep.entries), len(flat.entries) + 1)


if __name__ == "__main__":
    unittest.main()
