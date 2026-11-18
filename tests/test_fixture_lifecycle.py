"""Proof for fixture ownership, cleanup, and Windows junction handling."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fixture_lifecycle import TemporaryFixture, WORK

ROOT = Path(__file__).resolve().parents[1]


class FixtureLifecycleTests(unittest.TestCase):
    def test_cleans_empty_fixture_when_writing_receipt_fails(self):
        identifier = uuid4()
        expected = WORK / f"fx-{identifier.hex[:16]}"
        with (
            patch("fixture_lifecycle.uuid4", return_value=identifier),
            patch("fixture_lifecycle.json.dump", side_effect=OSError("controlled write failure")),
            self.assertRaisesRegex(OSError, "controlled write failure"),
        ):
            TemporaryFixture()
        self.assertFalse(expected.exists())
        self.assertFalse(expected.with_suffix(".json").exists())

    def test_cleans_a_successful_fixture(self):
        with TemporaryFixture() as directory:
            fixture = Path(directory)
            record = WORK / f"{fixture.name}.json"
            self.assertEqual(fixture.parent, WORK)
            self.assertEqual(json.loads(record.read_text())["name"], fixture.name)
            (fixture / "artifact.txt").write_text("owned")
        self.assertFalse(fixture.exists())
        self.assertFalse(record.exists())

    def test_cleans_after_an_exception(self):
        fixture = TemporaryFixture()
        with self.assertRaisesRegex(ValueError, "controlled failure"), fixture:
            raise ValueError("controlled failure")
        self.assertFalse(fixture.path.exists())
        self.assertFalse((WORK / f"{fixture.path.name}.json").exists())

    def test_cleans_after_a_child_times_out(self):
        fixture = TemporaryFixture()
        with self.assertRaises(subprocess.TimeoutExpired), fixture:
            subprocess.run(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                cwd=fixture.path,
                timeout=0.25,
                check=True,
            )
        self.assertFalse(fixture.path.exists())
        self.assertFalse((WORK / f"{fixture.path.name}.json").exists())

    @unittest.skipUnless(os.name == "nt", "Windows junction contract")
    def test_renderer_refuses_junction_and_fixture_cleanup_does_not_follow_it(self):
        with TemporaryFixture() as outside:
            target = Path(outside) / "result"
            target.mkdir()
            original = target / "untangle.html"
            original.write_text("keep this file", encoding="utf-8")
            with TemporaryFixture() as owned:
                junction = Path(owned) / "junction"
                subprocess.run(
                    [
                        "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                        "$ErrorActionPreference = 'Stop'; "
                        "New-Item -ItemType Junction -Path junction "
                        "-Target $env:UNTANGLE_JUNCTION_TEST_TARGET | Out-Null",
                    ],
                    cwd=owned,
                    env={**os.environ, "UNTANGLE_JUNCTION_TEST_TARGET": outside},
                    capture_output=True,
                    check=True,
                    timeout=10,
                )
                for flags in (["--dry-run", "--overwrite"], ["--overwrite"]):
                    with self.subTest(flags=flags):
                        run = subprocess.run(
                            [
                                sys.executable, str(ROOT / "skills/untangle/scripts/render_map.py"),
                                str(ROOT / "examples/evidence.json"),
                                "--output-dir", str(junction / "result"), "--json", *flags,
                            ],
                            capture_output=True,
                            text=True,
                            timeout=15,
                        )
                        self.assertEqual(run.returncode, 2, run.stderr)
                        self.assertEqual(json.loads(run.stdout)["error"]["code"], "safety_error")
                        self.assertIn("reparse point", run.stderr)
                        self.assertEqual(original.read_text(encoding="utf-8"), "keep this file")
                        self.assertEqual(list(target.iterdir()), [original])
            self.assertEqual(original.read_text(encoding="utf-8"), "keep this file")
