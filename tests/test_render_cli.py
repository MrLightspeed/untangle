"""Subprocess regressions for the renderer's documented CLI contract."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from fixture_lifecycle import TemporaryFixture

sys.dont_write_bytecode = True
SCRIPT = Path(__file__).resolve().parents[1] / "skills/untangle/scripts/render_map.py"
OUTPUT_NAMES = ("untangle.html", "comparison.svg", "map.json")


def manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "title": "CLI fixture",
        "scope": "A minimal renderer CLI test manifest",
        "features": [{"id": "orders", "label": "Orders"}],
        "knots": [],
        "before": {
            "revision": "fixture-before",
            "coverage": "The fixture contains no source files.",
            "files": [],
            "edges": [],
        },
        "after": None,
    }


class RenderCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryFixture()
        self.root = Path(self.temp.name).resolve()
        self.input = self.root / "evidence.json"
        self.input.write_text(json.dumps(manifest()), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *args: str | Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, str(SCRIPT), *(str(arg) for arg in args)],
            cwd=cwd or self.root,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )

    def json_value(self, output: str) -> dict[str, object]:
        self.assertTrue(output.endswith("\n"), output)
        self.assertEqual(output.count("\n"), 1, output)
        value = json.loads(output)
        self.assertIsInstance(value, dict)
        self.assertEqual(value.get("schema_version"), 1)
        return value

    def assert_json_error(self, process: subprocess.CompletedProcess[str], code: str) -> dict[str, object]:
        self.assertEqual(process.returncode, 2, process.stderr)
        self.assertNotEqual(process.stderr, "")
        self.assertNotIn("\x1b", process.stdout + process.stderr)
        value = self.json_value(process.stdout)
        self.assertFalse(value["ok"])
        self.assertEqual(value["mode"], "error")
        error = value["error"]
        self.assertIsInstance(error, dict)
        self.assertEqual(error["code"], code)
        return error

    def test_help_is_bounded_text_and_never_creates_output_paths(self):
        output_dir = self.root / "missing" / "page.html"
        process = self.run_cli("--json", "--help", "--output-dir", output_dir)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        self.assertTrue(process.stdout.startswith("usage: python render_map.py"))
        self.assertLess(len(process.stdout), 8_000)
        self.assertNotIn("\x1b", process.stdout)
        for text in (
            "Examples:",
            "--validate-only",
            "--dry-run",
            "--schema",
            "--help always prints bounded text",
            "Exit status: 0",
            "2 for input, argument, safety, or filesystem errors",
        ):
            self.assertIn(text, process.stdout)
        self.assertFalse(output_dir.exists())

    def test_schema_export_is_standalone_and_side_effect_free(self):
        process = self.run_cli("--schema")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        schema = json.loads(process.stdout)
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(len(schema["oneOf"]), 4)
        error_schema = schema["$defs"]["error"]
        self.assertEqual(
            error_schema["properties"]["code"]["enum"],
            ["input_error", "argument_error", "safety_error", "filesystem_error", "cancelled"],
        )
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["evidence.json"])

    def test_json_mode_and_schema_mode_conflict_with_exact_correction(self):
        process = self.run_cli("--schema", "--json")
        error = self.assert_json_error(process, "argument_error")
        self.assertIn("remove --json", error["hint"])

    def test_check_alias_validates_without_rendering_or_creating_output(self):
        workdir = self.root / "work"
        workdir.mkdir()
        process = self.run_cli(self.input, "--validate-only", "--json", cwd=workdir)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        value = self.json_value(process.stdout)
        self.assertEqual(value["mode"], "check")
        self.assertEqual(value["result"], {"input": str(self.input), "valid": True})
        self.assertEqual(list(workdir.iterdir()), [])
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["evidence.json", "work"])

    def test_check_rejects_output_options_without_creating_them(self):
        output_dir = self.root / "not-created"
        process = self.run_cli(self.input, "--check", "--output-dir", output_dir, "--json")
        error = self.assert_json_error(process, "argument_error")
        self.assertIn("Remove --output-dir", error["hint"])
        self.assertFalse(output_dir.exists())

    def test_dry_run_lists_three_paths_and_allows_folder_names_with_suffixes(self):
        output_dir = self.root / "page.html"
        process = self.run_cli(self.input, "--dry-run", "--output-dir", output_dir, "--json")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        value = self.json_value(process.stdout)
        self.assertEqual(value["mode"], "dry-run")
        result = value["result"]
        self.assertEqual(result["input"], str(self.input))
        self.assertEqual(
            result["outputs"],
            [{"path": str(output_dir / name), "action": "create"} for name in OUTPUT_NAMES],
        )
        self.assertFalse(output_dir.exists())

    def test_human_dry_run_shows_paths_and_actions_without_writes(self):
        output_dir = self.root / "preview"
        process = self.run_cli(self.input, "--dry-run", "--output-dir", output_dir)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("Plan (no files written):", process.stdout)
        self.assertEqual(process.stdout.count("CREATE"), 3)
        for name in OUTPUT_NAMES:
            self.assertIn(str(output_dir / name), process.stdout)
        self.assertFalse(output_dir.exists())
        self.assertNotIn("\x1b", process.stdout + process.stderr)

    def test_dry_run_collision_is_a_safety_error_and_preserves_existing_file(self):
        output_dir = self.root / "existing"
        output_dir.mkdir()
        existing = output_dir / "comparison.svg"
        existing.write_text("keep", encoding="utf-8")
        process = self.run_cli(self.input, "--dry-run", "--output-dir", output_dir, "--json")
        error = self.assert_json_error(process, "safety_error")
        self.assertIn(str(output_dir), error["context"])
        self.assertIn("fresh --output-dir", error["hint"])
        self.assertEqual(existing.read_text(encoding="utf-8"), "keep")
        self.assertEqual(sorted(path.name for path in output_dir.iterdir()), ["comparison.svg"])

    def test_dry_run_overwrite_previews_replacements_without_mutation(self):
        output_dir = self.root / "existing"
        output_dir.mkdir()
        existing = output_dir / "untangle.html"
        existing.write_text("keep", encoding="utf-8")
        process = self.run_cli(self.input, "--dry-run", "--overwrite", "--output-dir", output_dir, "--json")
        self.assertEqual(process.returncode, 0, process.stderr)
        outputs = self.json_value(process.stdout)["result"]["outputs"]
        self.assertEqual(
            outputs,
            [
                {"path": str(output_dir / "untangle.html"), "action": "replace"},
                {"path": str(output_dir / "comparison.svg"), "action": "create"},
                {"path": str(output_dir / "map.json"), "action": "create"},
            ],
        )
        self.assertEqual(existing.read_text(encoding="utf-8"), "keep")
        self.assertEqual(sorted(path.name for path in output_dir.iterdir()), ["untangle.html"])

    def test_json_errors_distinguish_schema_and_bad_json_with_file_location(self):
        invalid_schema = self.root / "invalid-schema.json"
        invalid_schema.write_text("{}", encoding="utf-8")
        schema_process = self.run_cli(invalid_schema, "--check", "--json")
        schema_error = self.assert_json_error(schema_process, "input_error")
        self.assertIn(str(invalid_schema), schema_error["context"])
        self.assertIn("schema_version", schema_error["message"])

        invalid_json = self.root / "invalid-json.json"
        invalid_json.write_text("{\n  nope\n}", encoding="utf-8")
        json_process = self.run_cli(invalid_json, "--json")
        json_error = self.assert_json_error(json_process, "input_error")
        self.assertIn(str(invalid_json), json_error["message"])
        self.assertIn("line 2, column 3", json_error["message"])

        duplicate_keys = self.root / "duplicate-keys.json"
        duplicate_keys.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        duplicate_process = self.run_cli(duplicate_keys, "--check", "--json")
        duplicate_error = self.assert_json_error(duplicate_process, "input_error")
        self.assertIn(str(duplicate_keys), duplicate_error["context"])
        self.assertIn("duplicate JSON object key", duplicate_error["message"])

    def test_missing_input_json_names_current_directory_and_next_step(self):
        process = self.run_cli("missing.json", "--json")
        error = self.assert_json_error(process, "filesystem_error")
        self.assertIn("missing.json", error["context"])
        self.assertIn(str(self.root), error["hint"])
        self.assertIn("absolute path", error["hint"])

    def test_json_filesystem_failure_keeps_the_primary_write_error(self):
        output_dir = self.root / "write-failure"
        driver = """\
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("render_map", sys.argv[1])
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)

def fail_stage(*_args):
    raise OSError("fixture write failure")

renderer._stage_file = fail_stage
raise SystemExit(renderer.main([sys.argv[2], "--output-dir", sys.argv[3], "--json"]))
"""
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        process = subprocess.run(
            [sys.executable, "-B", "-c", driver, str(SCRIPT), str(self.input), str(output_dir)],
            cwd=self.root,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        error = self.assert_json_error(process, "filesystem_error")
        self.assertIn("could not write outputs", error["message"])
        self.assertIn("fixture write failure", error["message"])
        self.assertIn(str(output_dir), error["context"])
        self.assertEqual(list(output_dir.iterdir()), [])

    def test_json_bare_invocation_and_unknown_flag_errors_are_actionable(self):
        missing = self.run_cli("--json")
        missing_error = self.assert_json_error(missing, "argument_error")
        self.assertIn("PATH_TO_MANIFEST", missing_error["hint"])

        unknown = self.run_cli(self.input, "--output-dri", "preview", "--json")
        unknown_error = self.assert_json_error(unknown, "argument_error")
        self.assertIn("--output-dir", unknown_error["hint"])
        self.assertNotIn("\x1b", unknown.stderr)

    def test_named_input_and_second_positional_paths_get_safe_corrections(self):
        named = self.run_cli("--input", self.input, "--json")
        named_error = self.assert_json_error(named, "argument_error")
        self.assertIn("positional", named_error["hint"])

        output_dir = self.root / "page.html"
        second = self.run_cli(self.input, output_dir, "--json")
        second_error = self.assert_json_error(second, "argument_error")
        self.assertIn("--output-dir", second_error["hint"])
        self.assertFalse(output_dir.exists())

    def test_conflicting_modes_have_an_exact_safe_correction(self):
        process = self.run_cli(self.input, "--check", "--dry-run", "--json")
        error = self.assert_json_error(process, "argument_error")
        self.assertIn("Remove --dry-run to validate only", error["hint"])

    def test_legacy_render_exit_codes_prefix_flags_and_artifacts_are_stable(self):
        first = self.root / "first"
        second = self.root / "second"
        structured = self.root / "structured"
        process_a = self.run_cli(self.input, "--output-dir", first)
        process_b = self.run_cli(self.input, "--out", second)
        process_json = self.run_cli(self.input, "--output-dir", structured, "--json")
        for process in (process_a, process_b):
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertTrue(process.stdout.startswith("Rendered: "))
            self.assertEqual(process.stderr, "")
            self.assertNotIn("\x1b", process.stdout)
        self.assertEqual(process_json.returncode, 0, process_json.stderr)
        self.assertEqual(process_json.stderr, "")
        self.assertNotIn("\x1b", process_json.stdout)
        structured_result = self.json_value(process_json.stdout)
        self.assertEqual(structured_result["mode"], "render")
        self.assertEqual(structured_result["result"]["input"], str(self.input))
        self.assertEqual(
            structured_result["result"]["outputs"],
            [{"path": str(structured / name), "action": "create"} for name in OUTPUT_NAMES],
        )
        for output_dir in (first, second, structured):
            self.assertEqual(sorted(path.name for path in output_dir.iterdir()), sorted(OUTPUT_NAMES))
        for name in OUTPUT_NAMES:
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes(), name)
            self.assertEqual((first / name).read_bytes(), (structured / name).read_bytes(), name)

    def test_legacy_collision_stays_exit_two_and_overwrite_remains_opt_in(self):
        output_dir = self.root / "existing"
        output_dir.mkdir()
        existing = output_dir / "comparison.svg"
        existing.write_text("keep", encoding="utf-8")

        blocked = self.run_cli(self.input, "--output-dir", output_dir)
        self.assertEqual(blocked.returncode, 2)
        self.assertEqual(blocked.stdout, "")
        self.assertIn("fresh --output-dir", blocked.stderr)
        self.assertEqual(existing.read_text(encoding="utf-8"), "keep")
        self.assertEqual(sorted(path.name for path in output_dir.iterdir()), ["comparison.svg"])

        replaced = self.run_cli(self.input, "--output-dir", output_dir, "--overwrite")
        self.assertEqual(replaced.returncode, 0, replaced.stderr)
        self.assertTrue(replaced.stdout.startswith("Rendered: "))
        self.assertEqual(sorted(path.name for path in output_dir.iterdir()), sorted(OUTPUT_NAMES))
        self.assertNotEqual(existing.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
