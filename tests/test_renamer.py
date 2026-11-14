import os
import tempfile
import unittest
from pathlib import Path

from mkvsd.renamer import (
    RenameRules, RStatus, apply_renames, build_plan, execute_plan, list_files, name_problem,
    parse_extensions,
)


def touch(base, *names):
    paths = []
    for n in names:
        p = Path(base) / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(n, encoding="utf-8")
        paths.append(p)
    return paths


class RulesTests(unittest.TestCase):
    def test_spec_example_keeps_extension(self):
        plan_rules = RenameRules(removals=["[1080p_]"])
        with tempfile.TemporaryDirectory() as tmp:
            (p,) = touch(tmp, "Titulo chulo [1080p_] 2026.mkv")
            plan = build_plan([p], plan_rules)
            self.assertEqual(plan.items[0].new_name, "Titulo chulo 2026.mkv")
            self.assertEqual(plan.items[0].status, RStatus.CHANGE)

    def test_multiple_removals(self):
        r = RenameRules(removals=["[1080p]", "WEB-DL", "x264"])
        self.assertEqual(r.apply("Serie WEB-DL [1080p] x264 E01"), "Serie E01")

    def test_removal_is_literal_and_case_insensitive_by_default(self):
        r = RenameRules(removals=["(1+1)"])
        self.assertEqual(r.apply("A (1+1) B"), "A B")
        r = RenameRules(removals=["web-dl"])
        self.assertEqual(r.apply("A WEB-DL B"), "A B")
        r = RenameRules(removals=["web-dl"], case_sensitive=True)
        self.assertEqual(r.apply("A WEB-DL B"), "A WEB-DL B")

    def test_replacement_literal_does_not_interpret_backslashes(self):
        r = RenameRules(replacements=[(".", " "), ("x", r"\1")])
        self.assertEqual(r.apply("a.bxc"), r"a b\1c")

    def test_regex_removal_and_replacement_with_groups(self):
        r = RenameRules(removals=[r"\[\d+p_?\]"], use_regex=True)
        self.assertEqual(r.apply("Titulo [1080p_] 2026"), "Titulo 2026")
        r = RenameRules(replacements=[(r"S(\d+)E(\d+)", r"\1x\2")], use_regex=True)
        self.assertEqual(r.apply("Serie S01E05"), "Serie 01x05")

    def test_regex_validation(self):
        self.assertIsNone(RenameRules(removals=["[abc"]).validate())      # literal: válido
        self.assertIn("no válida", RenameRules(removals=["[abc"], use_regex=True).validate())
        bad_group = RenameRules(replacements=[("(a)", r"\2")], use_regex=True)
        self.assertIsNotNone(bad_group.validate())

    def test_cleanup_spaces_duplicates_brackets_edges(self):
        r = RenameRules(removals=["1080p"])
        self.assertEqual(r.apply("  Serie   [1080p]  E01 "), "Serie E01")
        self.assertEqual(r.apply("Serie.. E01 -- final"), "Serie. E01 - final")
        self.assertEqual(r.apply("Serie - [1080p]"), "Serie")
        self.assertEqual(RenameRules().apply("Mission Impossible book"), "Mission Impossible book")  # no toca letras

    def test_cleanup_can_be_disabled(self):
        r = RenameRules(removals=["X"], collapse_spaces=False, collapse_duplicates=False,
                        remove_empty_brackets=False, trim_edge_separators=False)
        self.assertEqual(r.apply("A  X  B"), "A    B")

    def test_prefix_suffix_go_around_stem_not_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            (p,) = touch(tmp, "Ep 01.mkv")
            plan = build_plan([p], RenameRules(prefix="Serie - ", suffix=" [ES]"))
            self.assertEqual(plan.items[0].new_name, "Serie - Ep 01 [ES].mkv")

    def test_rule_never_touches_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            (p,) = touch(tmp, "Ep mkv 01.mkv")
            plan = build_plan([p], RenameRules(removals=["mkv"]))
            self.assertEqual(plan.items[0].new_name, "Ep 01.mkv")

    def test_name_problems(self):
        self.assertIsNone(name_problem("Serie 01.mkv"))
        self.assertIn("vacío", name_problem(".mkv"))
        self.assertIn("no permitidos", name_problem("a:b.mkv"))
        self.assertIn("reservado", name_problem("con.mkv"))
        self.assertIn("terminar", name_problem("abc."))

    def test_name_that_becomes_empty_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            (p,) = touch(tmp, "[1080p].mkv")
            plan = build_plan([p], RenameRules(removals=["[1080p]"]))
            self.assertEqual(plan.items[0].status, RStatus.INVALID)
            self.assertEqual(execute_plan(plan), [])
            self.assertTrue(p.exists())

    def test_invalid_result_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            (p,) = touch(tmp, "Serie 01.mkv")
            plan = build_plan([p], RenameRules(replacements=[(" ", ":")]))
            self.assertEqual(plan.items[0].status, RStatus.INVALID)


class ListingTests(unittest.TestCase):
    def test_extensions_recursive_hidden_and_natural_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch(tmp, "E10.mkv", "E2.mkv", "E1.MKV", "a.srt", "b.txt", ".oculto.mkv", "sub/E3.mp4")
            exts = parse_extensions("mkv, .srt", ["mp4"])
            self.assertEqual(exts, frozenset({".mkv", ".srt", ".mp4"}))
            rec = [p.name for p in list_files(tmp, True, exts)]
            self.assertEqual(rec, ["a.srt", "E1.MKV", "E2.mkv", "E10.mkv", "E3.mp4"])
            flat = [p.name for p in list_files(tmp, False, exts)]
            self.assertNotIn("E3.mp4", flat)
            self.assertNotIn(".oculto.mkv", [p.name for p in list_files(tmp, True, None)])
            self.assertIn("b.txt", [p.name for p in list_files(tmp, True, None)])


class PlanTests(unittest.TestCase):
    def test_duplicates_are_blocked_and_nothing_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = touch(tmp, "Serie [A].mkv", "Serie [B].mkv")
            plan = build_plan([a, b], RenameRules(removals=["[A]", "[B]"]))
            self.assertEqual([i.status for i in plan.items], [RStatus.CONFLICT_DUP] * 2)
            self.assertEqual(execute_plan(plan), [])
            self.assertTrue(a.exists() and b.exists())

    def test_existing_file_blocks_even_if_filtered_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            (a,) = touch(tmp, "Serie [x].mkv")
            touch(tmp, "Serie.mkv")                    # existe y no está en la lista
            plan = build_plan([a], RenameRules(removals=["[x]"]))
            self.assertEqual(plan.items[0].status, RStatus.CONFLICT_EXISTS)

    def test_same_name_in_different_folders_is_fine(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = touch(tmp, "s1/E01 [x].mkv", "s2/E01 [x].mkv")
            plan = build_plan([a, b], RenameRules(removals=["[x]"]))
            self.assertEqual(plan.count(RStatus.CHANGE), 2)

    def test_chain_inside_plan_is_allowed_and_executes(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = touch(tmp, "a.mkv", "ba.mkv")
            plan = build_plan([a, b], RenameRules(prefix="b"))       # a -> ba, ba -> bba
            self.assertEqual(plan.count(RStatus.CHANGE), 2)
            self.assertTrue(all(o.ok for o in execute_plan(plan)))
            self.assertEqual(sorted(os.listdir(tmp)), ["ba.mkv", "bba.mkv"])
            self.assertEqual((Path(tmp) / "ba.mkv").read_text(encoding="utf-8"), "a.mkv")

    def test_unchanged_file_keeps_its_name_reserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = touch(tmp, "A.mkv", "B.mkv")
            plan = build_plan([a, b], RenameRules(replacements=[("A", "B")]))
            st = {i.path.name: i.status for i in plan.items}
            self.assertEqual(st["A.mkv"], RStatus.CONFLICT_EXISTS)


class ExecuteTests(unittest.TestCase):
    def test_execute_renames_and_keeps_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = touch(tmp, "Ep 01 [x].mkv", "Ep 02 [x].mkv")
            plan = build_plan([a, b], RenameRules(removals=["[x]"]))
            out = execute_plan(plan)
            self.assertTrue(all(o.ok for o in out))
            self.assertEqual(sorted(os.listdir(tmp)), ["Ep 01.mkv", "Ep 02.mkv"])
            self.assertEqual((Path(tmp) / "Ep 01.mkv").read_text(encoding="utf-8"), "Ep 01 [x].mkv")

    def test_chain_rename_via_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = touch(tmp, "1.mkv", "2.mkv")
            out = apply_renames([(a, Path(tmp) / "2.mkv"), (b, Path(tmp) / "3.mkv")])
            self.assertTrue(all(o.ok for o in out))
            self.assertEqual((Path(tmp) / "2.mkv").read_text(encoding="utf-8"), "1.mkv")
            self.assertEqual((Path(tmp) / "3.mkv").read_text(encoding="utf-8"), "2.mkv")
            self.assertEqual(sorted(os.listdir(tmp)), ["2.mkv", "3.mkv"])

    def test_swap_via_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = touch(tmp, "a.mkv", "b.mkv")
            out = apply_renames([(a, b), (b, a)])
            self.assertTrue(all(o.ok for o in out))
            self.assertEqual((Path(tmp) / "a.mkv").read_text(encoding="utf-8"), "b.mkv")
            self.assertEqual((Path(tmp) / "b.mkv").read_text(encoding="utf-8"), "a.mkv")

    def test_case_only_rename(self):
        with tempfile.TemporaryDirectory() as tmp:
            (a,) = touch(tmp, "episodio.mkv")
            plan = build_plan([a], RenameRules(replacements=[("episodio", "Episodio")]))
            self.assertEqual(plan.items[0].status, RStatus.CHANGE)
            self.assertTrue(execute_plan(plan)[0].ok)
            self.assertEqual(os.listdir(tmp), ["Episodio.mkv"])

    def test_case_only_rename_is_direct_even_on_case_insensitive_fs(self):
        """En Windows lexists(destino) es True para un cambio de mayúsculas: debe permitirse solo si es el mismo archivo."""
        from unittest import mock
        src, dst = Path("/x/episodio.mkv"), Path("/x/Episodio.mkv")
        with mock.patch("os.path.lexists", return_value=True), mock.patch("os.path.samefile", return_value=True), \
                mock.patch("os.rename") as ren:
            out = apply_renames([(src, dst)])
        self.assertTrue(out[0].ok)
        ren.assert_called_once_with(src, dst)
        with mock.patch("os.path.lexists", return_value=True), mock.patch("os.path.samefile", return_value=False), \
                mock.patch("os.rename") as ren:
            out = apply_renames([(src, dst)])          # otro archivo distinto con ese nombre: nunca se pisa
        self.assertFalse(out[0].ok)
        ren.assert_not_called()

    def test_never_overwrites_if_target_appears_after_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            (a,) = touch(tmp, "A [x].mkv")
            plan = build_plan([a], RenameRules(removals=["[x]"]))
            (Path(tmp) / "A.mkv").write_text("otro", encoding="utf-8")   # aparece después de previsualizar
            out = execute_plan(plan)
            self.assertFalse(out[0].ok)
            self.assertEqual((Path(tmp) / "A.mkv").read_text(encoding="utf-8"), "otro")
            self.assertTrue(a.exists())

    def test_failed_temp_phase_restores_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = touch(tmp, "1.mkv", "2.mkv")
            blocker = Path(tmp) / "9.mkv"
            out = apply_renames([(a, b), (b, blocker)])     # b->9 funciona, a->b funciona (cadena)
            self.assertTrue(all(o.ok for o in out))
            # ahora un destino que ya existe y no se libera
            c = Path(tmp) / "c.mkv"; c.write_text("c", encoding="utf-8")
            out = apply_renames([(c, blocker)])
            self.assertFalse(out[0].ok)
            self.assertTrue(c.exists() and blocker.exists())


if __name__ == "__main__":
    unittest.main()
