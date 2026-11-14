import os
import tempfile
import unittest
from pathlib import Path

from mkvsd import rename_history as rh
from mkvsd.renamer import RenameRules, build_plan, execute_plan


def touch(base, *names):
    out = []
    for n in names:
        p = Path(base) / n
        p.write_text(n, encoding="utf-8")
        out.append(p)
    return out


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.TemporaryDirectory()
        self.work = tempfile.TemporaryDirectory()
        os.environ["MKVSD_DATA_DIR"] = self.data.name

    def tearDown(self):
        self.data.cleanup()
        self.work.cleanup()

    def _rename(self, rules, *names):
        files = touch(self.work.name, *names)
        out = execute_plan(build_plan(files, rules))
        rh.record_rename(out, self.work.name)
        return out

    def test_nothing_to_undo(self):
        self.assertTrue(rh.undo_last().nothing_to_undo)

    def test_undo_restores_names_and_is_not_repeatable(self):
        self._rename(RenameRules(removals=["[x]"]), "A [x].mkv", "B [x].mkv")
        self.assertEqual(sorted(os.listdir(self.work.name)), ["A.mkv", "B.mkv"])
        rep = rh.undo_last()
        self.assertEqual((rep.reverted, rep.failed), (2, []))
        self.assertEqual(sorted(os.listdir(self.work.name)), ["A [x].mkv", "B [x].mkv"])
        self.assertTrue(rh.undo_last().nothing_to_undo)

    def test_undo_only_last_operation(self):
        self._rename(RenameRules(removals=["[x]"]), "A [x].mkv")
        self._rename(RenameRules(suffix=" ES"), "C.mkv")
        rh.undo_last()
        self.assertEqual(sorted(os.listdir(self.work.name)), ["A.mkv", "C.mkv"])
        rh.undo_last()
        self.assertEqual(sorted(os.listdir(self.work.name)), ["A [x].mkv", "C.mkv"])

    def test_undo_does_not_overwrite_and_keeps_pending(self):
        self._rename(RenameRules(removals=["[x]"]), "A [x].mkv", "B [x].mkv")
        Path(self.work.name, "A [x].mkv").write_text("intruso", encoding="utf-8")  # ocupa el nombre original
        rep = rh.undo_last()
        self.assertEqual(rep.reverted, 1)
        self.assertEqual(len(rep.failed), 1)
        self.assertEqual(Path(self.work.name, "A [x].mkv").read_text(encoding="utf-8"), "intruso")
        self.assertTrue(Path(self.work.name, "A.mkv").exists())
        entry = rh.last_undoable()                       # lo que falló sigue pendiente
        self.assertEqual(len(entry.pending), 1)
        Path(self.work.name, "A [x].mkv").unlink()
        self.assertEqual(rh.undo_last().reverted, 1)
        self.assertTrue(rh.undo_last().nothing_to_undo)

    def test_undo_missing_file_is_reported(self):
        self._rename(RenameRules(removals=["[x]"]), "A [x].mkv")
        Path(self.work.name, "A.mkv").unlink()
        rep = rh.undo_last()
        self.assertEqual(rep.reverted, 0)
        self.assertEqual(len(rep.failed), 1)

    def test_undo_chain(self):
        files = touch(self.work.name, "a.mkv", "ba.mkv")
        rh.record_rename(execute_plan(build_plan(files, RenameRules(prefix="b"))), self.work.name)
        self.assertEqual(sorted(os.listdir(self.work.name)), ["ba.mkv", "bba.mkv"])
        self.assertEqual(rh.undo_last().reverted, 2)
        self.assertEqual(sorted(os.listdir(self.work.name)), ["a.mkv", "ba.mkv"])
        self.assertEqual(Path(self.work.name, "a.mkv").read_text(encoding="utf-8"), "a.mkv")

    def test_corrupt_line_is_ignored(self):
        self._rename(RenameRules(removals=["[x]"]), "A [x].mkv")
        with open(rh.history_path(), "a", encoding="utf-8") as fh:
            fh.write("{esto no es json\n")
        self.assertEqual(len(rh.load_history()), 1)

    def test_failed_renames_are_not_recorded(self):
        self.assertIsNone(rh.record_rename([]))

    def test_disabled_history_records_nothing(self):
        rh.set_enabled(False)
        try:
            self._rename(RenameRules(prefix="x "), "A.mkv")
        finally:
            rh.set_enabled(True)
        self.assertEqual(os.listdir(self.work.name), ["x A.mkv"])   # el renombrado sí se hace
        self.assertEqual(rh.load_history(), [])
        self.assertTrue(rh.undo_last().nothing_to_undo)

    def test_clear_history(self):
        self._rename(RenameRules(prefix="x "), "A.mkv")
        self._rename(RenameRules(prefix="y "), "B.mkv")
        self.assertEqual(rh.clear_history(), 2)
        self.assertEqual(rh.load_history(), [])
        self.assertIsNone(rh.last_undoable())
        self.assertEqual(rh.clear_history(), 0)      # sin archivo tampoco falla


if __name__ == "__main__":
    unittest.main()
