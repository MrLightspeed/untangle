"""Real-signal subprocess regressions for renderer publication cancellation."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
import unittest
from collections.abc import Callable
from pathlib import Path

from fixture_lifecycle import TemporaryFixture

sys.dont_write_bytecode = True
SCRIPT = (Path(__file__).resolve().parents[1] / "skills/untangle/scripts/render_map.py").resolve()
OUTPUT_NAMES = ("untangle.html", "comparison.svg", "map.json")
CHECKPOINT_DRIVER = textwrap.dedent(
    """
    import importlib.util
    import os
    from pathlib import Path
    import signal
    import sys

    script, manifest, output_dir, ready = (Path(arg).resolve() for arg in sys.argv[1:5])
    overwrite, json_output = (arg == "1" for arg in sys.argv[5:7])
    spec = importlib.util.spec_from_file_location("render_map", script)
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)

    publish = renderer._publish_no_clobber
    publish_calls = 0

    def checkpoint_after_first_publish(source, target):
        global publish_calls
        publish_calls += 1
        if publish_calls == 2:
            ready.write_text("ready\\n", encoding="ascii")
            if os.name == "nt":
                if sys.stdin.buffer.read(1) != b"x":
                    raise RuntimeError("missing cancellation checkpoint release")
                # Exercise Python's process-local SIGINT dispatch, not a console event.
                signal.raise_signal(signal.SIGINT)
            else:
                signal.pause()
        return publish(source, target)

    renderer._publish_no_clobber = checkpoint_after_first_publish
    arguments = [str(manifest), "--output-dir", str(output_dir)]
    if overwrite:
        arguments.append("--overwrite")
    if json_output:
        arguments.append("--json")
    raise SystemExit(renderer.main(arguments))
    """
).strip()


def manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "title": "Cancellation fixture",
        "scope": "A minimal renderer cancellation test manifest",
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


class RenderCancellationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryFixture()
        self.root = Path(self.temp.name).resolve()
        self.input = (self.root / "evidence.json").resolve()
        self.input.write_text(json.dumps(manifest()), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def cancel_at_checkpoint(
        self,
        *,
        overwrite: bool = False,
        json_output: bool = False,
        before_signal: Callable[[Path], None] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        output_dir = (self.root / "out").resolve()
        ready = (self.root / "published.ready").resolve()
        command = [
            sys.executable,
            "-c",
            CHECKPOINT_DRIVER,
            str(SCRIPT),
            str(self.input),
            str(output_dir),
            str(ready),
            "1" if overwrite else "0",
            "1" if json_output else "0",
        ]
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        process = subprocess.Popen(
            command,
            cwd=self.root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            deadline = time.monotonic() + 10.0
            while not ready.is_file():
                if process.poll() is not None:
                    stdout, stderr = process.communicate(timeout=2)
                    self.fail(
                        "renderer child exited before its publication checkpoint "
                        f"(exit {process.returncode}); stdout={stdout!r}; stderr={stderr!r}"
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.fail("renderer child did not reach its publication checkpoint within 10 seconds")
                time.sleep(min(0.01, remaining))

            first_output = output_dir / OUTPUT_NAMES[0]
            self.assertTrue(first_output.is_file(), "the first output must be published at the checkpoint")
            if before_signal is not None:
                before_signal(output_dir)

            if os.name == "nt":
                assert process.stdin is not None
                process.stdin.write("x")
                process.stdin.flush()
            else:
                os.kill(process.pid, signal.SIGINT)

            stdout, stderr = process.communicate(timeout=10)
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    def assert_no_traceback(self, stderr: str) -> None:
        self.assertNotIn("Traceback (most recent call last)", stderr)
        self.assertLess(len(stderr), 2_000, stderr)

    def test_fresh_output_cancellation_removes_published_and_staged_files(self) -> None:
        completed = self.cancel_at_checkpoint()

        self.assertEqual(completed.returncode, 130, completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assertIn("render cancelled", completed.stderr)
        self.assert_no_traceback(completed.stderr)
        self.assertTrue((self.root / "out").is_dir())
        self.assertEqual(list((self.root / "out").iterdir()), [])

    def test_overwrite_cancellation_restores_original_outputs_and_json_error(self) -> None:
        output_dir = (self.root / "out").resolve()
        output_dir.mkdir()
        originals = {name: f"original bytes for {name}\n".encode() for name in OUTPUT_NAMES}
        for name, content in originals.items():
            (output_dir / name).write_bytes(content)

        completed = self.cancel_at_checkpoint(overwrite=True, json_output=True)

        self.assertEqual(completed.returncode, 130, completed.stderr)
        self.assertNotEqual(completed.stderr, "")
        self.assert_no_traceback(completed.stderr)
        self.assertEqual(completed.stdout.count("\n"), 1, completed.stdout)
        envelope = json.loads(completed.stdout)
        self.assertEqual(envelope["schema_version"], 1)
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["mode"], "error")
        self.assertEqual(envelope["error"]["code"], "cancelled")
        self.assertEqual(
            {name: (output_dir / name).read_bytes() for name in OUTPUT_NAMES},
            originals,
        )
        self.assertEqual(sorted(path.name for path in output_dir.iterdir()), sorted(OUTPUT_NAMES))

    def test_concurrent_edit_survives_with_reported_recovery_copy(self) -> None:
        output_dir = (self.root / "out").resolve()
        output_dir.mkdir()
        originals = {name: f"original bytes for {name}\n".encode() for name in OUTPUT_NAMES}
        for name, content in originals.items():
            (output_dir / name).write_bytes(content)
        concurrent_edit = b"concurrent edit made at the publication checkpoint\n"

        def edit_first_output(root: Path) -> None:
            (root / OUTPUT_NAMES[0]).write_bytes(concurrent_edit)

        completed = self.cancel_at_checkpoint(overwrite=True, before_signal=edit_first_output)

        self.assertEqual(completed.returncode, 130, completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assert_no_traceback(completed.stderr)
        self.assertEqual((output_dir / OUTPUT_NAMES[0]).read_bytes(), concurrent_edit)
        for name in OUTPUT_NAMES[1:]:
            self.assertEqual((output_dir / name).read_bytes(), originals[name])
        recovery_copies = list(output_dir.glob(".untangle-backup-untangle.html-*.tmp"))
        self.assertEqual(len(recovery_copies), 1)
        recovery_copy = recovery_copies[0].resolve()
        self.assertEqual(recovery_copy.read_bytes(), originals[OUTPUT_NAMES[0]])
        self.assertIn(str(recovery_copy), completed.stderr)


if __name__ == "__main__":
    unittest.main()
