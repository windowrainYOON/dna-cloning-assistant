"""The dmg filename carries the version, so keep the two declarations in step."""

import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.version import __version__  # noqa: E402


class TestVersion(unittest.TestCase):
    def test_looks_like_a_release(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_pyproject_agrees(self):
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
            declared = re.search(r'^version = "(.+?)"', fh.read(), re.M)
        self.assertIsNotNone(declared)
        self.assertEqual(declared.group(1), __version__)

    def test_no_browser_engine_is_bundled(self):
        """The UI is tkinter; nothing may pull a web view back in."""
        with open(os.path.join(ROOT, "build", "build_macos.sh"), encoding="utf-8") as fh:
            script = fh.read()
        for banned in ("pyobjc-framework-WebKit", "webview", "chromium", "electron"):
            self.assertNotIn(banned, script)
        self.assertFalse(os.path.exists(os.path.join(ROOT, "app", "static")))

    def test_build_script_reads_the_package(self):
        """It must import app.version, not scrape quotes out of the file."""
        with open(os.path.join(ROOT, "build", "build_macos.sh"), encoding="utf-8") as fh:
            script = fh.read()
        self.assertIn("from app.version import __version__", script)


if __name__ == "__main__":
    unittest.main()
