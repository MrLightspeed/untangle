"""Regression tests for payload-test launcher startup and exit handling."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from contributor_runtimes import ROOT, runtime_commands
from fixture_lifecycle import TemporaryFixture

LAUNCHER = ROOT / "scripts/run-skill-payload-tests.mjs"
RUNTIMES = runtime_commands()


DRIVER = r"""
import childProcess from "node:child_process";
import { pathToFileURL } from "node:url";
import { writeFileSync } from "node:fs";
import path from "node:path";

const [launcherPath, runtime, outcome, recordPath, ...launcherArgs] = process.argv.slice(2);
const childExecutable = `${runtime.toLowerCase()}-test-runtime`;

if (outcome === "real-startup-failure") {
  process.execPath = path.join(path.dirname(recordPath), "missing-child-runtime.exe");
} else {
  process.execPath = childExecutable;
  childProcess.spawnSync = (executable, args, options) => {
    writeFileSync(
      recordPath,
      JSON.stringify({
        executable,
        args,
        cwd: options.cwd,
        stdio: options.stdio,
        windowsHide: options.windowsHide,
        argv0: options.argv0,
      }),
    );
    if (outcome === "spawn-throws") {
      const error = new Error("injected spawn failure detail");
      error.code = "EACCES";
      throw error;
    }
    if (outcome === "spawn-error") {
      const error = new Error("injected returned spawn failure detail");
      error.code = "ENOENT";
      return { error };
    }
    if (outcome === "missing-status") return {};
    if (outcome === "child-nonzero") return { status: 7, signal: null };
    if (outcome === "signal") return { status: null, signal: "SIGTERM" };
    return { status: 0, signal: null };
  };
}

process.argv = [process.execPath, launcherPath, ...launcherArgs];
await import(`${pathToFileURL(launcherPath).href}?launcher-test=${outcome}`);
"""


def command_environment(*, path: str | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if path is not None:
        environment["PATH"] = path
    return environment


def run_command(
    command: list[str], *, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        env=environment or command_environment(),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )


class LauncherFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryFixture()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.driver = self.directory / "launcher-driver.mjs"
        self.driver.write_text(DRIVER, encoding="utf-8")
        self.record_number = 0

    def run_driver(
        self,
        executable: str,
        runtime: str,
        outcome: str,
        *launcher_args: str,
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        self.record_number += 1
        record = self.directory / f"spawn-{self.record_number}.json"
        completed = run_command(
            [
                executable,
                str(self.driver),
                str(LAUNCHER),
                runtime,
                outcome,
                str(record),
                *launcher_args,
            ]
        )
        return completed, record

    def assert_startup_failure(
        self, completed: subprocess.CompletedProcess[str], runtime: str, code: str
    ) -> None:
        self.assertEqual(completed.returncode, 3, completed.stderr)
        self.assertEqual(completed.stdout, "")
        recovery = "bun run test" if runtime == "Bun" else "npm test"
        self.assertEqual(
            completed.stderr,
            f"Could not start the selected {runtime} test runner ({code}).\n"
            f"Try: {recovery}\n",
        )
        self.assertLessEqual(len(completed.stderr.encode("utf-8")), 256)

    def assert_spawn_request(self, record: Path, runtime: str) -> None:
        self.assertTrue(record.is_file(), "launcher did not call spawnSync")
        request = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual(request["executable"], f"{runtime.lower()}-test-runtime")
        expected_args = (
            ["test", "./tests/skill-payload.test.mjs"]
            if runtime == "Bun"
            else ["--test", "tests/skill-payload.test.mjs"]
        )
        self.assertEqual(request["args"], expected_args)
        self.assertEqual(Path(request["cwd"]).resolve(), ROOT.resolve())
        self.assertEqual(request["stdio"], "inherit")
        self.assertTrue(request["windowsHide"])
        self.assertEqual(request.get("argv0"), "bun" if runtime == "Bun" else None)

    def test_actual_child_startup_failure_returns_exit_three(self) -> None:
        for runtime, executable in RUNTIMES:
            with self.subTest(runtime=runtime):
                completed, record = self.run_driver(
                    executable, runtime, "real-startup-failure"
                )
                self.assert_startup_failure(completed, runtime, "ENOENT")
                self.assertFalse(record.exists(), "the real spawn must not be replaced")

    def test_current_runtime_starts_when_path_prefers_a_bun_stub(self) -> None:
        project = self.directory / "project"
        (project / "scripts").mkdir(parents=True)
        (project / "tests").mkdir()
        launcher = project / "scripts/run-skill-payload-tests.mjs"
        shutil.copy2(LAUNCHER, launcher)
        (project / "tests/skill-payload.test.mjs").write_text(
            'import test from "node:test";\n'
            'test("isolated runtime launch fixture", () => {});\n',
            encoding="utf-8",
        )
        shadow = self.directory / "shadow"
        shadow.mkdir()
        stub_name = "bun.exe" if os.name == "nt" else "bun"
        stub = shadow / stub_name
        if os.name == "nt":
            shutil.copy2(ROOT / "node_modules/bun/bin/bun.exe", stub)
        else:
            stub.write_text("#!/bin/sh\nexit 111\n", encoding="utf-8")
            stub.chmod(0o755)
        path = str(shadow)
        for runtime, executable in RUNTIMES:
            with self.subTest(runtime=runtime):
                completed = run_command(
                    [executable, str(launcher)],
                    environment=command_environment(path=path),
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertNotIn("Could not start", completed.stderr)
                self.assertIn("isolated runtime launch fixture", completed.stdout + completed.stderr)

    def test_injected_spawn_failure_paths_return_exit_three(self) -> None:
        scenarios = [
            ("spawn-throws", "EACCES"),
            ("spawn-error", "ENOENT"),
            ("missing-status", "child exited without a status"),
        ]
        for runtime, executable in RUNTIMES:
            for outcome, code in scenarios:
                with self.subTest(runtime=runtime, outcome=outcome):
                    completed, record = self.run_driver(
                        executable, runtime, outcome
                    )
                    self.assert_startup_failure(completed, runtime, code)
                    self.assert_spawn_request(record, runtime)

    def test_child_nonzero_status_is_preserved(self) -> None:
        for runtime, executable in RUNTIMES:
            with self.subTest(runtime=runtime):
                completed, record = self.run_driver(
                    executable, runtime, "child-nonzero"
                )
                self.assertEqual(completed.returncode, 7, completed.stderr)
                self.assertEqual(completed.stdout, "")
                self.assertEqual(completed.stderr, "")
                self.assert_spawn_request(record, runtime)

    def test_signal_result_maps_status_and_reports_recovery(self) -> None:
        for runtime, executable in RUNTIMES:
            with self.subTest(runtime=runtime):
                completed, record = self.run_driver(
                    executable, runtime, "signal"
                )
                recovery = "bun run test" if runtime == "Bun" else "npm test"
                self.assertEqual(completed.returncode, 143, completed.stderr)
                self.assertEqual(
                    completed.stderr,
                    f"The selected {runtime} test runner was interrupted by "
                    f"SIGTERM (exit 143).\nTry: {recovery}\n",
                )
                self.assertLessEqual(len(completed.stderr.encode("utf-8")), 256)
                self.assert_spawn_request(record, runtime)

    def test_help_remains_quiet_and_does_not_spawn(self) -> None:
        for runtime, executable in RUNTIMES:
            with self.subTest(runtime=runtime):
                completed, record = self.run_driver(
                    executable, runtime, "success", "--help"
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stderr, "")
                self.assertIn("Exit codes:", completed.stdout)
                self.assertIn("tests/skill-payload.test.mjs", completed.stdout)
                self.assertFalse(record.exists(), "--help must not call spawnSync")


if __name__ == "__main__":
    unittest.main()
