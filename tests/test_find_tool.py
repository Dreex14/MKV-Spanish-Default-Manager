import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mkvsd import mkvtools

EXE = "mkvmerge" + (".exe" if os.name == "nt" else "")


def make_tool(folder: Path) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / EXE).write_bytes(b"")
    return str(folder / EXE)


class FindToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # Entorno vacío: sin PATH ni instalaciones, para que solo cuente lo que crea cada prueba
        self.env = mock.patch.dict(os.environ, {"ProgramFiles": str(self.root / "pf"),
                                                "ProgramFiles(x86)": str(self.root / "pf86"),
                                                "LOCALAPPDATA": str(self.root / "local")})
        self.env.start()
        self.which = mock.patch("shutil.which", return_value=None)
        self.which.start()

    def tearDown(self):
        self.which.stop()
        self.env.stop()
        if hasattr(sys, "_MEIPASS"):
            del sys._MEIPASS
        self.tmp.cleanup()

    def test_custom_dir_wins_over_path(self):
        custom = make_tool(self.root / "elegida")
        with mock.patch("shutil.which", return_value=str(self.root / "path" / EXE)):
            self.assertEqual(mkvtools.find_tool("mkvmerge", str(self.root / "elegida")), custom)

    def test_invalid_custom_dir_falls_back(self):
        installed = make_tool(self.root / "pf" / "MKVToolNix")
        self.assertEqual(mkvtools.find_tool("mkvmerge", str(self.root / "no-existe")), installed)

    def test_installed_wins_over_bundled(self):
        installed = make_tool(self.root / "pf" / "MKVToolNix")
        make_tool(self.root / "meipass" / "MKVToolNix")
        sys._MEIPASS = str(self.root / "meipass")
        self.assertEqual(mkvtools.find_tool("mkvmerge"), installed)

    def test_bundled_is_last_resort(self):
        bundled = make_tool(self.root / "meipass" / "MKVToolNix")
        sys._MEIPASS = str(self.root / "meipass")
        found = mkvtools.find_tool("mkvmerge")
        self.assertEqual(found, bundled)
        self.assertTrue(mkvtools.is_bundled(found))

    def test_nothing_found(self):
        self.assertIsNone(mkvtools.find_tool("mkvmerge"))
        self.assertFalse(mkvtools.is_bundled(str(self.root / EXE)))


if __name__ == "__main__":
    unittest.main()
