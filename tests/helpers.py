"""Test helpers: load the skill scripts by path and build throwaway skills."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent

GOOD_FRONTMATTER = """---
name: {name}
description: >-
  Converts CSV exports into tidy Markdown tables. Use when the user asks to
  turn a spreadsheet export or CSV file into a table for a document.
---
"""
GOOD_BODY = """
# CSV to table

Read the CSV file the user named, check that every row has the same number of
columns, then write a Markdown table with a header row and aligned columns.
Report the row count when finished.
"""


def load_script(relative: str):
    """Import a script from the repository by its path."""
    path = ROOT / relative
    sys.path.insert(0, str(path.parent))
    try:
        name = "metaskills_" + path.stem
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(path.parent))


def run_main(module, argv):
    """Run a script's main() and return (exit status, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            status = module.main(argv)
        except SystemExit as exit_:  # argparse errors
            status = exit_.code
    return status, out.getvalue(), err.getvalue()


class SkillCase(unittest.TestCase):
    """Base class giving each test an empty temporary directory."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def make_skill(self, name="csv-table", skill_md=None, files=None, parent=None):
        """Create a skill directory; skill_md=None writes a valid one."""
        directory = (parent or self.tmp) / name
        directory.mkdir(parents=True, exist_ok=True)
        if skill_md is None:
            skill_md = GOOD_FRONTMATTER.format(name=name) + GOOD_BODY
        (directory / "SKILL.md").write_text(skill_md, encoding="utf-8")
        for relative, content in (files or {}).items():
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content, encoding="utf-8")
        return directory
