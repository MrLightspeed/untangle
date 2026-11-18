"""Subprocess regressions for the pinned native Bun format and lint CLIs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from contributor_runtimes import ROOT, local_bun_info, runtime_commands
from fixture_lifecycle import TemporaryFixture

FORMAT_SCRIPT = ROOT / "scripts/format.mjs"
LINT_SCRIPT = ROOT / "scripts/lint.mjs"
LOCAL_BUN_SCRIPT = ROOT / "scripts/local-bun.mjs"
RUNTIMES = runtime_commands()
LOCAL_BUN = local_bun_info()


def run_command(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(NO_COLOR="1", CI="1", TERM="dumb")
    if environment:
        env.update(environment)
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def make_project(root: Path, *, with_binary: bool) -> Path:
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(LOCAL_BUN_SCRIPT, scripts / "local-bun.mjs")
    shutil.copy2(FORMAT_SCRIPT, scripts / "format.mjs")
    shutil.copy2(LINT_SCRIPT, scripts / "lint.mjs")
    pin = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))[
        "devDependencies"
    ]["bun"]
    package = {"private": True, "devDependencies": {"bun": pin}}
    (root / "package.json").write_text(
        json.dumps(package, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy2(ROOT / ".prettierrc.json", root / ".prettierrc.json")
    if with_binary:
        if LOCAL_BUN is None:
            raise RuntimeError("The pinned local Bun dependency is required.")
        binary = Path(LOCAL_BUN["executable"]).resolve()
        package_json = ROOT / "node_modules/bun/package.json"
        node_modules = root / "node_modules"
        bun_package = node_modules / "bun"
        platform_package = node_modules / Path(LOCAL_BUN["packageName"])
        # Hard links
        # avoid copying the large executable while preserving a real subprocess.
        bun_package.mkdir(parents=True)
        shutil.copy2(package_json, bun_package / "package.json")
        source_platform = ROOT / "node_modules" / Path(LOCAL_BUN["packageName"])
        platform_package.mkdir(parents=True)
        shutil.copy2(source_platform / "package.json", platform_package / "package.json")
        binary_dir = platform_package / "bin"
        binary_dir.mkdir()
        os.link(binary, binary_dir / binary.name)
    return root


def mapping_project(root: Path) -> Path:
    root.mkdir(parents=True)
    package_names = {
        "@oven/bun-windows-x64",
        "@oven/bun-windows-aarch64",
        "@oven/bun-darwin-x64",
        "@oven/bun-darwin-aarch64",
        "@oven/bun-linux-x64",
        "@oven/bun-linux-aarch64",
        "@oven/bun-linux-x64-musl",
        "@oven/bun-linux-aarch64-musl",
        "@oven/bun-freebsd-x64",
        "@oven/bun-freebsd-aarch64",
        "@oven/bun-linux-x64-android",
        "@oven/bun-linux-aarch64-android",
    }
    pin = "0.0.0-fixture"
    (root / "package.json").write_text(
        json.dumps({"devDependencies": {"bun": pin}}), encoding="utf-8"
    )
    bun_dir = root / "node_modules/bun"
    bun_dir.mkdir(parents=True)
    (bun_dir / "package.json").write_text(
        json.dumps(
            {
                "name": "bun",
                "version": pin + "+237bba5",
                "optionalDependencies": {
                    name: pin + "+237bba5" for name in sorted(package_names)
                },
            }
        ),
        encoding="utf-8",
    )
    for name in package_names:
        package = root / "node_modules" / Path(name)
        binary_name = "bun.exe" if "windows" in name else "bun"
        binary = package / "bin" / binary_name
        binary.parent.mkdir(parents=True)
        (package / "package.json").write_text(
            json.dumps({"name": name, "version": pin + "+237bba5"}),
            encoding="utf-8",
        )
        binary.write_bytes(b"fixture binary")
    shutil.copy2(LOCAL_BUN_SCRIPT, root / "local-bun.mjs")
    return root


class NativeBunCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryFixture()
        self.root = Path(self.temporary.name).resolve()
        self.outside = self.root / "outside"
        self.outside.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def invoke(
        self,
        runtime: tuple[str, str],
        command: str,
        *args: str,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return run_command(
            [runtime[1], str(self.root / "scripts" / f"{command}.mjs"), *args],
            cwd=self.outside,
            environment=environment,
        )

    def result(
        self,
        completed: subprocess.CompletedProcess[str],
        command: str,
    ) -> dict[str, object]:
        lines = completed.stdout.splitlines()
        self.assertEqual(len(lines), 1, completed.stdout)
        value = json.loads(lines[0])
        self.assertEqual(value["schema_version"], "1.0.0")
        self.assertEqual(value["command"], command)
        return value

    def test_help_is_quiet_and_available_before_local_dependencies(self) -> None:
        make_project(self.root, with_binary=False)
        for runtime in RUNTIMES:
            for command in ("format", "lint"):
                with self.subTest(runtime=runtime[0], command=command):
                    completed = self.invoke(runtime, command, "--help")
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertEqual(completed.stderr, "")
                    self.assertIn("Usage:", completed.stdout)
                    self.assertIn("Exit codes", completed.stdout)

    def test_missing_local_bun_returns_actionable_startup_result(self) -> None:
        make_project(self.root, with_binary=False)
        for command in ("format", "lint"):
            with self.subTest(command=command):
                completed = self.invoke(RUNTIMES[0], command, "--json")
                self.assertEqual(completed.returncode, 3, completed.stderr)
                value = self.result(completed, command)
                self.assertEqual(value["status"], "failed")
                self.assertIsNone(value["child_exit_code"])
                self.assertEqual(value["error"]["stage"], "local Bun startup")
                self.assertIn("npm ci --ignore-scripts", value["error"]["recovery"])

    def test_native_format_check_write_cycle_and_json_streams(self) -> None:
        make_project(self.root, with_binary=True)
        source = self.root / "fixture.js"
        original = b"const value='fixture';\n"
        source.write_bytes(original)
        runtimes = [runtime for runtime in RUNTIMES if runtime[0] in ("Node", "Bun")]
        stub_dir = self.root / "node_modules/.bin"
        stub_dir.mkdir(parents=True)
        stub_name = "bun.exe" if os.name == "nt" else "bun"
        shutil.copy2(ROOT / "node_modules/bun/bin/bun.exe", stub_dir / stub_name)
        shadowed_path = os.pathsep.join([str(stub_dir), os.environ.get("PATH", "")])

        for runtime in runtimes[:1]:
            with self.subTest(runtime=runtime[0]):
                source.write_bytes(original)
                before = source.read_bytes()
                checked = self.invoke(
                    runtime,
                    "format",
                    "--check",
                    "--json",
                    environment={"PATH": shadowed_path},
                )
                self.assertEqual(checked.returncode, 1, checked.stderr)
                self.assertEqual(source.read_bytes(), before)
                self.assertIn("Checking formatting", checked.stderr)
                self.assertNotIn("\x1b", checked.stdout + checked.stderr)
                failed = self.result(checked, "format")
                self.assertEqual(failed["mode"], "check")
                self.assertEqual(failed["child_exit_code"], 1)

                written = self.invoke(runtime, "format", "--write", "--json")
                self.assertEqual(written.returncode, 0, written.stderr)
                self.assertEqual(source.read_bytes(), b'const value = "fixture";\n')
                self.assertEqual(self.result(written, "format")["mode"], "write")

                first = self.invoke(runtime, "format", "--check", "--json")
                second = self.invoke(runtime, "format", "--json")
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertNotIn("\x1b", first.stdout + first.stderr)
                self.assertEqual(first.stdout, second.stdout)
                self.assertEqual(self.result(first, "format")["status"], "passed")

    def test_native_lint_reports_errors_without_modifying_sources(self) -> None:
        make_project(self.root, with_binary=True)
        source = self.root / "bug.js"
        original = b"debugger;\n"
        source.write_bytes(original)
        for runtime in RUNTIMES[:1]:
            with self.subTest(runtime=runtime[0]):
                before = source.read_bytes()
                completed = self.invoke(runtime, "lint", "--json")
                self.assertEqual(completed.returncode, 1, completed.stderr)
                self.assertEqual(source.read_bytes(), before)
                self.assertNotIn("\x1b", completed.stdout + completed.stderr)
                self.assertIn("no-debugger", completed.stderr)
                result = self.result(completed, "lint")
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["child_exit_code"], 1)
                repeated = self.invoke(runtime, "lint", "--json")
                self.assertEqual(repeated.returncode, 1, repeated.stderr)
                self.assertEqual(completed.stdout, repeated.stdout)
                self.assertEqual(source.read_bytes(), before)

    def test_platform_binary_mapping_includes_macos_and_linux_musl(self) -> None:
        mapping_root = self.root / "mapping"
        mapping_project(mapping_root)
        cases = [
            ("win32", "x64", None, "@oven/bun-windows-x64"),
            ("win32", "arm64", None, "@oven/bun-windows-aarch64"),
            ("darwin", "x64", None, "@oven/bun-darwin-x64"),
            ("darwin", "arm64", None, "@oven/bun-darwin-aarch64"),
            ("linux", "x64", "glibc", "@oven/bun-linux-x64"),
            ("linux", "arm64", "glibc", "@oven/bun-linux-aarch64"),
            ("linux", "x64", "musl", "@oven/bun-linux-x64-musl"),
            ("linux", "arm64", "musl", "@oven/bun-linux-aarch64-musl"),
            ("freebsd", "x64", None, "@oven/bun-freebsd-x64"),
            ("freebsd", "arm64", None, "@oven/bun-freebsd-aarch64"),
            ("android", "x64", None, "@oven/bun-linux-x64-android"),
            ("android", "arm64", None, "@oven/bun-linux-aarch64-android"),
        ]
        script = (
            f"import {{ resolveLocalBun }} from "
            f"{json.dumps((mapping_root / 'local-bun.mjs').as_uri())}; "
            "const cases = JSON.parse(process.argv[2]); "
            "const resolved = cases.map(([platform, arch, libc]) => "
            "resolveLocalBun({root: process.argv[3], platform, arch, libc})); "
            "let unsupported = false; "
            "try { resolveLocalBun({root: process.argv[3], platform: 'openbsd', arch: 'x64'}); } "
            "catch (error) { unsupported = error.message.includes('No local Bun package is configured'); } "
            "process.stdout.write(JSON.stringify({resolved, unsupported}));"
        )
        request_cases = [[platform, arch, libc] for platform, arch, libc, _ in cases]
        probe = mapping_root / "probe.mjs"
        probe.write_text(script, encoding="utf-8")
        completed = run_command(
            [RUNTIMES[0][1], str(probe), json.dumps(request_cases), str(mapping_root)],
            cwd=mapping_root,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(
            [item["packageName"] for item in result["resolved"]],
            [expected for _, _, _, expected in cases],
        )
        self.assertTrue(result["unsupported"])

    def test_format_arguments_fail_before_resolving_local_bun(self) -> None:
        make_project(self.root, with_binary=False)
        invalid = self.invoke(RUNTIMES[0], "format", "--chec", "--json")
        self.assertEqual(invalid.returncode, 2)
        result = self.result(invalid, "format")
        self.assertEqual(result["mode"], "error")
        self.assertIsNone(result["child_exit_code"])
        self.assertEqual(result["error"]["stage"], "arguments")

    def test_write_conflicts_and_lint_fix_flag_do_not_mutate_sources(self) -> None:
        make_project(self.root, with_binary=False)
        source = self.root / "bug.js"
        source.write_bytes(b"debugger;\n")
        before = source.read_bytes()

        conflict = self.invoke(
            RUNTIMES[0], "format", "--check", "--write", "--json"
        )
        self.assertEqual(conflict.returncode, 2)
        conflict_result = self.result(conflict, "format")
        self.assertEqual(conflict_result["mode"], "error")
        self.assertEqual(conflict_result["error"]["stage"], "arguments")
        self.assertEqual(source.read_bytes(), before)

        fixes = self.invoke(RUNTIMES[0], "lint", "--fix", "--json")
        self.assertEqual(fixes.returncode, 2)
        fix_result = self.result(fixes, "lint")
        self.assertEqual(fix_result["mode"], "error")
        self.assertEqual(fix_result["error"]["stage"], "arguments")
        self.assertIn('Unsupported lint argument "--fix"', fix_result["error"]["message"])
        self.assertIn("--json and --help", fix_result["error"]["message"])
        self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
