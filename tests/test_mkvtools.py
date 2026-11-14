import os
import tempfile
import unittest

from mkvsd.applier import apply_file
from mkvsd.models import Status as S
from mkvsd.mkvtools import MkvTools, MkvToolError, parse_tracks
from mkvsd.scanner import analyze_file, find_mkv_files

SAMPLE = {
    "container": {"recognized": True},
    "tracks": [
        {"id": 0, "type": "video", "codec": "HEVC", "properties": {"uid": 1}},
        {"id": 1, "type": "audio", "codec": "AAC", "properties": {"uid": 2, "language": "spa"}},
        {"id": 2, "type": "subtitles", "codec": "SubRip/SRT",
         "properties": {"uid": 11, "language": "eng", "track_name": "English", "default_track": False}},
        {"id": 3, "type": "subtitles", "codec": "SubRip/SRT",
         "properties": {"uid": 12, "language": "spa", "language_ietf": "es", "track_name": "ESP LAT",
                        "default_track": True}},
        {"id": 4, "type": "subtitles", "codec": "SubRip/SRT",
         "properties": {"uid": 13, "language": "spa", "track_name": "ESP", "default_track": False}},
    ],
}


class FakeTools(MkvTools):
    """MKVToolNix simulado: mantiene los indicadores en memoria."""

    def __init__(self, defaults, fail=False, ignore_edit=False):
        super().__init__("mkvmerge", "mkvpropedit")
        self.defaults, self.fail, self.ignore_edit, self.runs = dict(defaults), fail, ignore_edit, []

    def probe(self, path):
        import copy
        data = copy.deepcopy(SAMPLE)
        for tr in data["tracks"]:
            if tr["type"] == "subtitles":
                tr["properties"]["default_track"] = self.defaults[tr["properties"]["uid"]]
        return parse_tracks(data)

    def run_propedit(self, cmd):
        self.runs.append(cmd)
        if self.fail:
            raise MkvToolError("archivo bloqueado")
        if self.ignore_edit:
            return
        it = iter(cmd)
        for a in it:
            if a == "--edit":
                uid = int(next(it).split("=")[1])
                assert next(it) == "--set"
                self.defaults[uid] = next(it).endswith("=1")


class ToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["MKVSD_DATA_DIR"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_only_subtitles_with_numbering(self):
        tracks = parse_tracks(SAMPLE)
        self.assertEqual([(t.index, t.id, t.name) for t in tracks],
                         [(1, 2, "English"), (2, 3, "ESP LAT"), (3, 4, "ESP")])

    def test_command_uses_uid_selectors(self):
        tools = FakeTools({11: False, 12: True, 13: False})
        d = analyze_file(tools, "x.mkv").decision
        cmd = tools.build_propedit_cmd("x.mkv", d.changes)
        self.assertEqual(cmd[-8:], ["--edit", "track:=13", "--set", "flag-default=1",
                                    "--edit", "track:=12", "--set", "flag-default=0"])

    def test_dry_run_changes_nothing(self):
        tools = FakeTools({11: False, 12: True, 13: False})
        r = apply_file(tools, "x.mkv", dry_run=True)
        self.assertEqual(r.outcome, "simulated")
        self.assertEqual(tools.runs, [])
        self.assertEqual(tools.defaults, {11: False, 12: True, 13: False})

    def test_real_apply_and_idempotence(self):
        tools = FakeTools({11: False, 12: True, 13: False})
        self.assertEqual(apply_file(tools, "x.mkv", dry_run=False).outcome, "ok")
        self.assertEqual(tools.defaults, {11: False, 12: False, 13: True})
        self.assertEqual(apply_file(tools, "x.mkv", dry_run=False).outcome, "unchanged")
        self.assertEqual(len(tools.runs), 1)

    def test_tool_failure_is_reported(self):
        tools = FakeTools({11: False, 12: True, 13: False}, fail=True)
        self.assertEqual(apply_file(tools, "x.mkv", dry_run=False).outcome, "error")

    def test_verification_catches_ineffective_edit(self):
        tools = FakeTools({11: False, 12: True, 13: False}, ignore_edit=True)
        self.assertEqual(apply_file(tools, "x.mkv", dry_run=False).outcome, "error")

    def test_probe_error_becomes_error_status(self):
        class Broken(FakeTools):
            def probe(self, path):
                raise MkvToolError("no legible")
        a = analyze_file(Broken({}), "x.mkv")
        self.assertEqual(a.decision.status, S.ERROR)

    def test_find_files_recursive(self):
        os.makedirs(os.path.join(self.tmp.name, "a", "b"))
        for rel in ["one.mkv", "a/two.MKV", "a/b/three.mkv", "a/skip.mp4"]:
            open(os.path.join(self.tmp.name, rel), "w").close()
        self.assertEqual(len(find_mkv_files(self.tmp.name, True)), 3)
        self.assertEqual(len(find_mkv_files(self.tmp.name, False)), 1)


if __name__ == "__main__":
    unittest.main()
