"""Observable contracts for the contributor check/test orchestrator."""

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import unittest

from contributor_runtimes import runtime_commands
from fixture_lifecycle import TemporaryFixture


ROOT = Path(__file__).resolve().parents[1]
RUNTIMES = [executable for _, executable in runtime_commands()]


@unittest.skipUnless(RUNTIMES, "A contributor JavaScript runtime is required")
class CheckRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryFixture()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "scripts").mkdir()
        self.script = self.root / "scripts/run-checks.mjs"
        shutil.copy2(ROOT / "scripts/run-checks.mjs", self.script)

    def run_cli(self, runtime, *args, extra_env=None):
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1", NO_COLOR="1", CI="1", TERM="dumb")
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [runtime, str(self.script), *args], cwd=self.root, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, timeout=30,
        )

    def fixtures(self):
        for name, stage in (("format.mjs", "format"), ("lint.mjs", "lint"), ("check-package.mjs", "package"),
                            ("run-skill-payload-tests.mjs", "payload")):
            (self.root / "scripts" / name).write_text(
                'import fs from "node:fs";\n'
                f'fs.appendFileSync("calls.txt", "{stage}\\n");\n'
                f'console.log("{stage} child report");\n'
                f'if(fs.existsSync("fail-{stage}")) {{ console.error("primary {stage} failure"); process.exit(7); }}\n',
                encoding="utf-8",
            )
        (self.root / "tests").mkdir()
        (self.root / "tests/test_fixture.py").write_text(
            'from pathlib import Path\nimport unittest\n'
            'class Fixture(unittest.TestCase):\n'
            ' def test_behavior(self):\n'
            '  with Path("calls.txt").open("a") as f: f.write("python-tests\\n")\n'
            '  print("Python child report")\n', encoding="utf-8",
        )
        (self.root / "scripts/check-example.py").write_text(
            'from pathlib import Path\n'
            'with Path("calls.txt").open("a") as f: f.write("example\\n")\n'
            'print("example child report")\n', encoding="utf-8",
        )

    def test_help_and_plan_work_without_children_or_dependencies(self):
        for runtime in RUNTIMES:
            with self.subTest(runtime=Path(runtime).name):
                help_result = self.run_cli(runtime, "check", "--help")
                self.assertEqual(help_result.returncode, 0, help_result.stderr)
                self.assertEqual(help_result.stderr, "")
                self.assertIn("--plan", help_result.stdout)
                self.assertLess(len(help_result.stdout), 6000)
                plan = self.run_cli(runtime, "check", "--plan", "--json")
                self.assertEqual(plan.returncode, 0, plan.stderr)
                self.assertEqual(plan.stderr, "")
                result = json.loads(plan.stdout)
                self.assertEqual(result["status"], "planned")
                self.assertEqual([s["name"] for s in result["stages"]], ["format", "lint", "package", "payload", "python-tests", "example"])
                self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["scripts"])

    def test_json_run_is_stable_and_preserves_stage_order(self):
        self.fixtures()
        for runtime in RUNTIMES:
            with self.subTest(runtime=Path(runtime).name):
                (self.root / "calls.txt").write_text("", encoding="utf-8")
                first = self.run_cli(runtime, "check", "--json")
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertEqual(len(first.stdout.splitlines()), 1)
                result = json.loads(first.stdout)
                self.assertEqual(result["status"], "passed")
                self.assertIsNone(result["failed_stage"])
                self.assertEqual((self.root / "calls.txt").read_text().splitlines(), ["format", "lint", "package", "payload", "python-tests", "example"])
                self.assertIn("child report", first.stderr)
                self.assertIn("format: start", first.stderr)
                self.assertIn("example: passed", first.stderr)
                self.assertNotIn("\x1b", first.stdout + first.stderr)
                second = self.run_cli(runtime, "check", "--json")
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(first.stdout, second.stdout)

    def test_test_task_runs_only_its_three_original_stages(self):
        self.fixtures()
        result = self.run_cli(RUNTIMES[0], "test", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "calls.txt").read_text().splitlines(), ["payload", "python-tests", "example"])

    def test_first_failure_preserves_status_and_stops_later_stages(self):
        self.fixtures()
        (self.root / "fail-package").touch()
        for runtime in RUNTIMES:
            (self.root / "calls.txt").write_text("", encoding="utf-8")
            result = self.run_cli(runtime, "check", "--json")
            self.assertEqual(result.returncode, 7, result.stderr)
            value = json.loads(result.stdout)
            self.assertEqual(value["exit_code"], 7)
            self.assertEqual(value["failed_stage"], "package")
            self.assertEqual((self.root / "calls.txt").read_text().splitlines(), ["format", "lint", "package"])
            self.assertIn("primary package failure", result.stderr)
            self.assertIn("--plan", result.stderr)

    def test_invalid_arguments_do_not_start_children(self):
        for task in ("check", "test"):
            with self.subTest(task=task):
                result = self.run_cli(RUNTIMES[0], task, "--write", "--json")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["failed_stage"], "arguments")
                self.assertIn('Unknown argument "--write"', result.stderr)
                self.assertIn("--help, --plan, or --json", result.stderr)
                self.assertIn(f"scripts/run-checks.mjs {task} --help", result.stderr)
                self.assertFalse((self.root / "calls.txt").exists())
        conflict = self.run_cli(RUNTIMES[0], "check", "test", "--json")
        self.assertEqual(conflict.returncode, 2)
        self.assertIn("Choose exactly one task", conflict.stderr)
        self.assertIn("scripts/run-checks.mjs --help", conflict.stderr)
        self.assertFalse((self.root / "calls.txt").exists())

    def test_missing_python_reports_startup_failure_without_running_later_checks(self):
        self.fixtures()
        empty_path = self.root / "empty-path"
        empty_path.mkdir()
        result = self.run_cli(RUNTIMES[0], "test", "--json", extra_env={"PATH": str(empty_path)})
        self.assertEqual(result.returncode, 3, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["failed_stage"], "python-tests")
        self.assertEqual(value["exit_code"], 3)
        self.assertEqual((self.root / "calls.txt").read_text().splitlines(), ["payload"])
        self.assertIn("could not start", result.stderr)
        self.assertIn("--plan", result.stderr)


if __name__ == "__main__":
    unittest.main()
