import os
import tempfile
import unittest
from pathlib import Path

from mkvsd.batch import describe_result, process_files
from mkvsd.mkvtools import MkvTools, MkvToolError, parse_tracks

LAT_PLUS_ESP = [("English", "eng", False), ("ESP LAT", "spa", True), ("ESP", "spa", False), ("English Commentary", "eng", False)]
ONLY_ENG = [("English", "eng", True)]
ONLY_LAT = [("ESP LAT", "spa", True)]
FORCED_ONLY = [("ESP LAT", "spa", True), ("ESP Forzados", "spa", False)]


class MultiFake(MkvTools):
    """Varios 'archivos' con pistas distintas; el estado vive en memoria."""

    def __init__(self, files):
        super().__init__("mkvmerge", "mkvpropedit")
        self.files = {k: [list(t) for t in v] for k, v in files.items()}

    def probe(self, path):
        if str(path) not in self.files:
            raise MkvToolError("archivo ilegible")
        tracks = [{"id": 0, "type": "video", "properties": {"uid": 1}}]
        for i, (name, lang, default) in enumerate(self.files[str(path)], 1):
            tracks.append({"id": i, "type": "subtitles", "properties": {
                "uid": 100 + i, "track_name": name, "language": lang, "default_track": default}})
        return parse_tracks({"container": {"recognized": True}, "tracks": tracks})

    def run_propedit(self, cmd):
        tracks = self.files[cmd[3]]
        it = iter(cmd[4:])
        for a in it:
            if a == "--edit":
                uid = int(next(it).split("=")[1])
                next(it)
                tracks[uid - 101][2] = next(it).endswith("=1")


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["MKVSD_DATA_DIR"] = self.tmp.name
        files = {f"S01E{i:02d}.mkv": LAT_PLUS_ESP for i in range(1, 23)}   # 22 con castellano
        files["S01E23.mkv"] = ONLY_ENG
        files["S01E24.mkv"] = ONLY_LAT
        files["S01E25.mkv"] = FORCED_ONLY
        self.names = list(files) + ["roto.mkv"]
        self.tools = MultiFake(files)

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_run_summary_and_no_changes(self):
        s = process_files(self.tools, self.names, dry_run=True)
        self.assertEqual((s.found, s.analyzed, s.castellano_found, s.modified), (26, 25, 22, 22))
        self.assertEqual((s.without_castellano, s.review, s.errors), (2, 1, 1))
        self.assertTrue(self.tools.files["S01E01.mkv"][1][2])   # el latino sigue como predeterminado

    def test_real_run_modifies_all_and_keeps_tracks(self):
        results = []
        s = process_files(self.tools, self.names, dry_run=False, on_result=lambda r, i, n: results.append(r))
        self.assertEqual((s.modified, s.errors), (22, 1))
        for i in range(1, 23):
            tr = self.tools.files[f"S01E{i:02d}.mkv"]
            self.assertEqual(len(tr), 4)
            self.assertEqual([t[2] for t in tr], [False, False, True, False])
        self.assertEqual(self.tools.files["S01E24.mkv"], [list(t) for t in ONLY_LAT])
        # segunda pasada: todo ya correcto
        s2 = process_files(self.tools, self.names, dry_run=False)
        self.assertEqual((s2.modified, s2.already_ok), (0, 22))
        self.assertEqual(len(results), 26)

    def test_cancel(self):
        s = process_files(self.tools, self.names, dry_run=True, cancelled=lambda: True)
        self.assertTrue(s.cancelled)
        self.assertEqual(s.analyzed, 0)

    def test_log_line_names_selected_track(self):
        from mkvsd.applier import apply_file
        line = describe_result(apply_file(self.tools, "S01E01.mkv", dry_run=True))
        self.assertIn("#3 «ESP»", line)
        self.assertIn("#2 «ESP LAT»", line)


if __name__ == "__main__":
    unittest.main()
