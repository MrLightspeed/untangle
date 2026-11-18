"""Regression tests for the contributor check and test-runner CLIs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from contributor_runtimes import local_bun_info, runtime_commands
from fixture_lifecycle import TemporaryFixture


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
PINNED_GIT_BIN = Path("C:/Program Files/Git/cmd")


def command_environment() -> dict[str, str]:
    environment = os.environ.copy()
    if os.name == "nt" and (PINNED_GIT_BIN / "git.exe").is_file():
        environment["PATH"] = (
            f"{PINNED_GIT_BIN}{os.pathsep}{environment.get('PATH', '')}"
        )
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def run_command(
    command: list[str], *, cwd: Path = ROOT, timeout: int = 30
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=command_environment(),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def one_json_result(completed: subprocess.CompletedProcess[str]) -> dict:
    lines = completed.stdout.splitlines()
    if len(lines) != 1:
        raise AssertionError(f"expected one JSON line, received {len(lines)}")
    return json.loads(lines[0])


@unittest.skipUnless(NODE, "Node is required by the contributor package scripts")
class ContributorCliTests(unittest.TestCase):
    def run_node(self, script: Path, *args: str, cwd: Path = ROOT, timeout: int = 30):
        return run_command([NODE, str(script), *args], cwd=cwd, timeout=timeout)

    def run_python(self, script: Path, *args: str, cwd: Path = ROOT, timeout: int = 60):
        return run_command(
            [sys.executable, "-B", str(script), *args], cwd=cwd, timeout=timeout
        )

    def test_help_is_bounded_and_does_not_start_checks_or_tests(self) -> None:
        package = self.run_node(ROOT / "scripts/check-package.mjs", "--help", timeout=5)
        self.assertEqual(package.returncode, 0, package.stderr)
        self.assertEqual(package.stderr, "")
        self.assertIn("--json", package.stdout)
        self.assertIn("Exit codes:", package.stdout)
        self.assertNotIn("Package checks passed", package.stdout)
        self.assertNotIn("Markdown documents checked", package.stdout)

        example = self.run_python(ROOT / "scripts/check-example.py", "--help", timeout=5)
        self.assertEqual(example.returncode, 0, example.stderr)
        self.assertEqual(example.stderr, "")
        self.assertIn("--write-preview", example.stdout)
        self.assertIn("--json", example.stdout)
        self.assertIn("Exit codes:", example.stdout)
        self.assertNotIn("before:", example.stdout)
        self.assertNotIn("Ran ", example.stdout)

        launcher = self.run_node(
            ROOT / "scripts/run-skill-payload-tests.mjs", "--help", timeout=5
        )
        self.assertEqual(launcher.returncode, 0, launcher.stderr)
        self.assertEqual(launcher.stderr, "")
        self.assertIn("Exit codes:", launcher.stdout)
        self.assertNotIn("tests 3", launcher.stdout)
        self.assertNotIn("pass 3", launcher.stdout)

    def test_package_help_from_incomplete_checkout_keeps_startup_diagnostic(self) -> None:
        with TemporaryFixture() as temporary:
            copied_root = Path(temporary)
            copied_scripts = copied_root / "scripts"
            copied_scripts.mkdir()
            copied_script = copied_scripts / "check-package.mjs"
            shutil.copy2(ROOT / "scripts/check-package.mjs", copied_script)

            completed = self.run_node(copied_script, "--help", cwd=copied_root, timeout=5)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stderr, "")
            self.assertIn("Usage: node scripts/check-package.mjs", completed.stdout)
            self.assertNotIn("Package checks passed", completed.stdout)

            missing_dependencies = self.run_node(
                copied_script, "--json", cwd=copied_root
            )
            self.assertEqual(missing_dependencies.returncode, 1)
            self.assertEqual(missing_dependencies.stderr, "")
            result = one_json_result(missing_dependencies)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"]["stage"], "contributor dependencies")
            self.assertIn("check-skill-payload.mjs", result["error"]["message"])
            self.assertIn(
                "bun install --frozen-lockfile", result["error"]["recovery"]
            )
            self.assertIn("npm ci --ignore-scripts", result["error"]["recovery"])

    def test_unknown_arguments_give_an_exact_help_command(self) -> None:
        package = self.run_node(ROOT / "scripts/check-package.mjs", "--not-a-flag")
        self.assertEqual(package.returncode, 2)
        self.assertEqual(package.stdout, "")
        self.assertIn("Try: node scripts/check-package.mjs --help", package.stderr)

        example = self.run_python(ROOT / "scripts/check-example.py", "--not-a-flag")
        self.assertEqual(example.returncode, 2)
        self.assertEqual(example.stdout, "")
        self.assertIn("Try: python scripts/check-example.py --help", example.stderr)

        launcher = self.run_node(
            ROOT / "scripts/run-skill-payload-tests.mjs", "--not-a-flag"
        )
        self.assertEqual(launcher.returncode, 2)
        self.assertEqual(launcher.stdout, "")
        self.assertIn(
            "Try: node scripts/run-skill-payload-tests.mjs --help", launcher.stderr
        )

    def test_package_json_result_and_failure_are_single_objects(self) -> None:
        completed = self.run_node(ROOT / "scripts/check-package.mjs", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        result = one_json_result(completed)
        self.assertEqual(result["schema_version"], "1.0.0")
        self.assertEqual(result["command"], "check-package")
        self.assertEqual(result["status"], "passed")
        self.assertGreater(result["markdown_documents_checked"], 0)
        self.assertEqual(result["markdown_failures"], 0)

        with TemporaryFixture() as temporary:
            fixture = Path(temporary)
            scripts = fixture / "scripts"
            scripts.mkdir()
            shutil.copy2(ROOT / "scripts/check-package.mjs", scripts)
            shutil.copy2(ROOT / "scripts/check-skill-payload.mjs", scripts)
            unexpected = fixture / "skills/untangle/unexpected.txt"
            unexpected.parent.mkdir(parents=True)
            unexpected.write_text("fixture only\n", encoding="utf-8")

            failed = self.run_node(
                scripts / "check-package.mjs", "--json", cwd=fixture
            )
            self.assertEqual(failed.returncode, 1)
            self.assertEqual(failed.stderr, "")
            result = one_json_result(failed)
            self.assertEqual(result["schema_version"], "1.0.0")
            self.assertEqual(result["command"], "check-package")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"]["stage"], "skill package boundary")
            self.assertIn("unexpected.txt", result["error"]["message"])
            self.assertNotIn("at runChecks", failed.stdout)

            human_failure = self.run_node(scripts / "check-package.mjs", cwd=fixture)
            self.assertEqual(human_failure.returncode, 1)
            self.assertEqual(human_failure.stdout, "")
            self.assertIn(
                "Package check failed during skill package boundary",
                human_failure.stderr,
            )
            self.assertIn(
                "Try: node scripts/check-package.mjs --help", human_failure.stderr
            )
            self.assertNotIn("at runChecks", human_failure.stderr)

    def test_example_json_result_and_failure_keep_progress_off_stdout(self) -> None:
        completed = self.run_python(ROOT / "scripts/check-example.py", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = one_json_result(completed)
        self.assertEqual(result["schema_version"], "1.0.0")
        self.assertEqual(result["command"], "check-example")
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["feature_file_pairs_checked"], 12)
        self.assertIn("12 pairs before and 8 after", completed.stderr)
        self.assertFalse(result["preview_updated"])
        self.assertIn("before: Ran ", completed.stderr)
        self.assertIn("after: Ran ", completed.stderr)
        self.assertNotIn("Traceback", completed.stdout + completed.stderr)

        with TemporaryFixture() as temporary:
            fixture = Path(temporary)
            (fixture / "scripts").mkdir()
            (fixture / "examples").mkdir()
            shutil.copy2(ROOT / "scripts/check-example.py", fixture / "scripts")
            shutil.copytree(ROOT / "examples/checkout", fixture / "examples/checkout")
            shutil.copy2(ROOT / "examples/evidence.json", fixture / "examples")
            (fixture / "skills/untangle").mkdir(parents=True)
            shutil.copytree(
                ROOT / "skills/untangle/scripts", fixture / "skills/untangle/scripts"
            )
            (fixture / "assets").mkdir()
            shutil.copy2(ROOT / "assets/untangle-before-after.png", fixture / "assets")
            shutil.copy2(ROOT / "examples/preview-capture.json", fixture / "examples")
            preview = fixture / "assets/example-comparison.svg"
            preview.write_text("stale preview\n", encoding="utf-8")

            evidence = fixture / "examples/evidence.json"
            valid_evidence = evidence.read_text(encoding="utf-8")
            evidence.write_text("{\n", encoding="utf-8")
            human_failure = self.run_python(
                fixture / "scripts/check-example.py", cwd=fixture
            )
            self.assertEqual(human_failure.returncode, 1)
            self.assertEqual(human_failure.stdout, "")
            self.assertIn(
                "Example check failed during evidence manifest", human_failure.stderr
            )
            self.assertIn(
                "Try: python scripts/check-example.py --help", human_failure.stderr
            )
            self.assertNotIn("Traceback", human_failure.stderr)

            json_failure = self.run_python(
                fixture / "scripts/check-example.py", "--json", cwd=fixture
            )
            self.assertEqual(json_failure.returncode, 1)
            self.assertEqual(json_failure.stderr, "")
            result = one_json_result(json_failure)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(
                result["error"]["stage"], "evidence manifest and renderer validation"
            )
            self.assertIn("Expecting property name", result["error"]["message"])

            evidence.write_text(valid_evidence, encoding="utf-8")

            failed = self.run_python(
                fixture / "scripts/check-example.py", "--json", cwd=fixture
            )
            self.assertEqual(failed.returncode, 1)
            result = one_json_result(failed)
            self.assertEqual(result["schema_version"], "1.0.0")
            self.assertEqual(result["command"], "check-example")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"]["stage"], "renderer preview validation")
            self.assertIn("stale", result["error"]["message"])
            self.assertIn("before: Ran ", failed.stderr)
            self.assertIn("after: Ran ", failed.stderr)
            self.assertNotIn("Traceback", failed.stdout + failed.stderr)

            unrelated = fixture / "assets/keep.txt"
            unrelated.write_bytes(b"unrelated asset")
            regenerated = self.run_python(
                fixture / "scripts/check-example.py", "--write-preview", "--json", cwd=fixture
            )
            self.assertEqual(regenerated.returncode, 0, regenerated.stderr)
            regenerated_result = one_json_result(regenerated)
            self.assertEqual(regenerated_result["status"], "passed")
            self.assertTrue(regenerated_result["preview_updated"])
            self.assertEqual(
                preview.read_bytes(), (ROOT / "assets/example-comparison.svg").read_bytes()
            )
            self.assertEqual(unrelated.read_bytes(), b"unrelated asset")
            rechecked = self.run_python(
                fixture / "scripts/check-example.py", "--json", cwd=fixture
            )
            self.assertEqual(rechecked.returncode, 0, rechecked.stderr)
            self.assertFalse(one_json_result(rechecked)["preview_updated"])

            (fixture / "assets/untangle-before-after.png").write_bytes(b"different capture")
            stale_capture = self.run_python(
                fixture / "scripts/check-example.py", "--json", cwd=fixture
            )
            self.assertEqual(stale_capture.returncode, 1)
            error = one_json_result(stale_capture)["error"]
            self.assertEqual(error["stage"], "renderer preview validation")
            self.assertIn("differs from the recorded capture", error["message"])

    def test_launcher_runs_bun_test_through_the_forced_node_alias(self) -> None:
        info = local_bun_info()
        self.assertIsNotNone(info, "The pinned local Bun dependency is required")
        with TemporaryFixture() as temporary:
            fixture = Path(temporary)
            (fixture / "scripts").mkdir()
            (fixture / "tests").mkdir()
            shutil.copy2(
                ROOT / "scripts/run-skill-payload-tests.mjs",
                fixture / "scripts/run-skill-payload-tests.mjs",
            )
            (fixture / "package.json").write_text(
                json.dumps({"scripts": {"payload": "node scripts/run-skill-payload-tests.mjs"}}),
                encoding="utf-8",
            )
            (fixture / "tests/skill-payload.test.mjs").write_text(
                'import test from "node:test";\n'
                'test("forced Bun node alias runs the canonical suite", () => {});\n',
                encoding="utf-8",
            )
            completed = run_command(
                [info["executable"], "run", "--bun", "payload"], cwd=fixture
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("forced Bun node alias runs the canonical suite", completed.stdout + completed.stderr)

    def test_launcher_preserves_normal_owner_and_child_failure_status(self) -> None:
        runtimes = [(kind, [executable]) for kind, executable in runtime_commands()]

        with TemporaryFixture() as temporary:
            fixture = Path(temporary)
            scripts = fixture / "scripts"
            tests = fixture / "tests"
            scripts.mkdir()
            tests.mkdir()
            launcher = scripts / "run-skill-payload-tests.mjs"
            shutil.copy2(ROOT / "scripts/run-skill-payload-tests.mjs", launcher)
            suite = tests / "skill-payload.test.mjs"
            decoy = (
                fixture
                / "agent_ergonomics_audit/audit/baseline/tests/skill-payload.test.mjs"
            )
            decoy.parent.mkdir(parents=True)
            decoy.write_text(
                'import test from "node:test";\n'
                'test("audit decoy", () => { throw new Error("audit decoy marker"); });\n',
                encoding="utf-8",
            )

            for runtime_name, runtime in runtimes:
                with self.subTest(runtime=runtime_name, outcome="pass"):
                    suite.write_text(
                        'import test from "node:test";\n'
                        'test("canonical test file runs", () => {});\n',
                        encoding="utf-8",
                    )
                    passed = run_command([*runtime, str(launcher)], cwd=fixture)
                    self.assertEqual(passed.returncode, 0, passed.stderr)
                    self.assertIn(
                        "canonical test file runs", passed.stdout + passed.stderr
                    )
                    self.assertNotIn("audit decoy marker", passed.stdout + passed.stderr)

                with self.subTest(runtime=runtime_name, outcome="child failure"):
                    suite.write_text(
                        'import test from "node:test";\n'
                        'test("intentional child failure", () => { throw new Error("child failure marker"); });\n',
                        encoding="utf-8",
                    )
                    failed = run_command([*runtime, str(launcher)], cwd=fixture)
                    self.assertEqual(failed.returncode, 1)
                    self.assertIn("child failure marker", failed.stdout + failed.stderr)
                    self.assertNotIn("audit decoy marker", failed.stdout + failed.stderr)


if __name__ == "__main__":
    unittest.main()
