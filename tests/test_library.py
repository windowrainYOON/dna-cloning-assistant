"""The plasmid library folder: listing, persistence and opening through the API."""

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import settings  # noqa: E402

EXAMPLE = os.path.join(ROOT, "examples", "pET28a-6xHis-hPRD_ORF1_only.dna")


class TestLibrary(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.lib = tempfile.mkdtemp()
        self._env = {k: os.environ.get(k) for k in ("HOME", "XDG_CONFIG_HOME")}
        os.environ["HOME"] = self.home
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self.home, ".config")
        shutil.copy(EXAMPLE, os.path.join(self.lib, "pET28a.dna"))
        os.makedirs(os.path.join(self.lib, "project-a"))
        shutil.copy(EXAMPLE, os.path.join(self.lib, "project-a", "variant.dna"))
        os.makedirs(os.path.join(self.lib, "project-a", "deep"))
        shutil.copy(EXAMPLE, os.path.join(self.lib, "project-a", "deep", "too-far.dna"))
        with open(os.path.join(self.lib, "notes.txt"), "w") as fh:
            fh.write("not a plasmid")

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.lib, ignore_errors=True)

    def test_lists_dna_files_one_level_deep(self):
        settings.set_library_dir(self.lib)
        listing = settings.list_library()
        names = {f["name"] for f in listing["files"]}
        self.assertEqual(names, {"pET28a.dna", "variant.dna"})
        self.assertIsNone(listing["error"])
        folders = {f["name"]: f["folder"] for f in listing["files"]}
        self.assertEqual(folders["variant.dna"], "project-a")
        self.assertEqual(folders["pET28a.dna"], "")

    def test_folder_is_remembered(self):
        settings.set_library_dir(self.lib)
        self.assertEqual(settings.library_dir(), os.path.abspath(self.lib))
        with open(settings.config_path(), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["library_dir"], os.path.abspath(self.lib))
        settings.clear_library_dir()
        self.assertIsNone(settings.library_dir())

    def test_missing_folder_is_reported_not_raised(self):
        settings.set_library_dir(self.lib)
        shutil.rmtree(self.lib)
        listing = settings.list_library()
        self.assertEqual(listing["files"], [])
        self.assertIn("찾을 수 없습니다", listing["error"])

    def test_setting_a_missing_folder_is_rejected(self):
        with self.assertRaises(ValueError):
            settings.set_library_dir(os.path.join(self.home, "nope"))

    def test_recent_files_are_newest_first_and_deduplicated(self):
        a = os.path.join(self.lib, "pET28a.dna")
        b = os.path.join(self.lib, "project-a", "variant.dna")
        settings.note_recent(a)
        settings.note_recent(b)
        settings.note_recent(a)
        self.assertEqual([r["path"] for r in settings.recent_files()],
                         [os.path.abspath(a), os.path.abspath(b)])

    def test_new_file_shows_up_without_resetting_the_folder(self):
        settings.set_library_dir(self.lib)
        shutil.copy(EXAMPLE, os.path.join(self.lib, "added-later.dna"))
        names = {f["name"] for f in settings.list_library()["files"]}
        self.assertIn("added-later.dna", names)


if __name__ == "__main__":
    unittest.main()
