"""Tests for install.py. Standard library only, temp destinations only.

No test writes to the repository source tree or to a global skills directory.

    python3 -m unittest discover -s tests -v
"""

import importlib.util
import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("install_script", REPO / "install.py")
install = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(install)


def source_fingerprint():
    """File count and total size of the repository source tree."""
    count = 0
    total = 0
    for path in install.SOURCE.rglob("*"):
        if path.is_file():
            count += 1
            total += path.stat().st_size
    return count, total


def call(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = install.main(list(argv))
    return code, out.getvalue() + err.getvalue()


class TempDestTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="install-test-"))
        self.dest = self.tmp / "skills"
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class DestinationGuard(TempDestTestCase):
    """A destination that overlaps the source must be refused before any change."""

    def assert_source_intact(self, *argv):
        before = source_fingerprint()
        code, text = call(*argv)
        self.assertEqual(code, 2, text)
        self.assertEqual(source_fingerprint(), before)
        return text

    def test_dest_is_source(self):
        text = self.assert_source_intact("--dest", str(install.SOURCE), "--force")
        self.assertIn("source directory", text)

    def test_dest_inside_source(self):
        target = install.SOURCE / install.available()[0] / "nested"
        self.assert_source_intact("--dest", str(target), "--force")

    def test_dest_contains_source(self):
        self.assert_source_intact("--dest", str(REPO), "--force")

    def test_unknown_skill_name(self):
        self.assert_source_intact("--dest", str(self.dest), "--only", "not-a-skill")


class InstallBehaviour(TempDestTestCase):
    def test_dry_run_creates_nothing(self):
        code, text = call("--dest", str(self.dest), "--dry-run")
        self.assertEqual(code, 0, text)
        self.assertIn("would copy", text)
        self.assertFalse(self.dest.exists())

    def test_copy_then_skip_then_force(self):
        code, _ = call("--dest", str(self.dest), "--only", "web-qa")
        self.assertEqual(code, 0)
        self.assertTrue((self.dest / "web-qa" / "SKILL.md").is_file())

        code, text = call("--dest", str(self.dest), "--only", "web-qa")
        self.assertEqual(code, 1)
        self.assertIn("use --force", text)

        marker = self.dest / "web-qa" / "stale.md"
        marker.write_text("stale")
        code, _ = call("--dest", str(self.dest), "--only", "web-qa", "--force")
        self.assertEqual(code, 0)
        self.assertFalse(marker.exists())

    def test_link_mode(self):
        code, _ = call("--dest", str(self.dest), "--only", "jev", "--link")
        self.assertEqual(code, 0)
        link = self.dest / "jev"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (install.SOURCE / "jev").resolve())

    def test_install_all_names(self):
        code, _ = call("--dest", str(self.dest))
        self.assertEqual(code, 0)
        installed = sorted(p.name for p in self.dest.iterdir())
        self.assertEqual(installed, install.available())

    def test_copy_drops_local_state(self):
        junk = self.tmp / "junk"
        (junk / "skills" / "demo" / "__pycache__").mkdir(parents=True)
        (junk / "skills" / "demo" / "__pycache__" / "x.pyc").write_text("x")
        (junk / "skills" / "demo" / ".env").write_text("SECRET=1")
        (junk / "skills" / "demo" / ".env.local").write_text("SECRET=1")
        (junk / "skills" / "demo" / ".env.example").write_text("SECRET=")
        (junk / "skills" / "demo" / "logs").mkdir()
        (junk / "skills" / "demo" / "logs" / "run.log").write_text("x")
        (junk / "skills" / "demo" / "SKILL.md").write_text("ok")
        out = self.tmp / "out"
        shutil.copytree(junk / "skills" / "demo", out, ignore=install.skip_entries)
        self.assertTrue((out / "SKILL.md").is_file())
        self.assertTrue((out / ".env.example").is_file())
        for gone in ("__pycache__", ".env", ".env.local", "logs"):
            self.assertFalse((out / gone).exists(), gone)


if __name__ == "__main__":
    unittest.main()
