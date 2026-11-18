"""Regression checks for evidence visibility and recoverable output writes."""

from __future__ import annotations

import contextlib
import errno
import importlib.util
import io
import json
import stat
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET
from unittest import mock

from fixture_lifecycle import TemporaryFixture

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location(
    "render_map",
    Path(__file__).resolve().parents[1] / "skills/untangle/scripts/render_map.py",
)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


class FileRecords(HTMLParser):
    def __init__(self):
        super().__init__()
        self.records = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "li" and "file-record" in attributes.get("class", "").split():
            self.current = {"attributes": attributes, "text": ""}

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data

    def handle_endtag(self, tag):
        if tag == "li" and self.current is not None:
            self.records.append(self.current)
            self.current = None


def manifest():
    files = [f"source/module{index}.ext" for index in range(19)]
    return {
        "schema_version": 1, "title": "Fixture", "scope": "Unresolved paths remain visible",
        "features": [{"id": "feature", "label": "Feature"}], "knots": [],
        "before": {
            "revision": "fixture-before", "coverage": "Only the first file has proven reachability.",
            "files": files,
            "edges": [{"feature": "feature", "file": files[0], "evidence": [{
                "path": files[0], "line": 1, "note": "Fixture registration", "kind": "configured",
            }]}],
        },
        "after": None,
    }


class RenderMapTests(unittest.TestCase):
    def test_knot_categories_round_trip_and_render(self):
        categories = (
            "leaky-abstraction", "drifted-duplication", "stale-workaround",
            "empty-wrapper", "dependency-cycle", "mixed-responsibilities",
        )
        raw = manifest()
        raw["knots"] = [
            {
                "id": index,
                "category": category,
                "severity": "medium",
                "title": f"Fixture {category}",
                "features": ["feature"],
                "locations": [{"path": "source/module0.ext", "line": index}],
                "evidence": "Fixture evidence with a specific source location.",
                "remedy": "Fixture remedy.",
                "status": "open",
                "verification": [],
            }
            for index, category in enumerate(categories, start=1)
        ]
        data = renderer.validate_manifest(raw)
        self.assertEqual(tuple(knot["category"] for knot in data["knots"]), categories)

        with TemporaryFixture() as directory:
            evidence = Path(directory) / "evidence.json"
            output = Path(directory) / "rendered"
            evidence.write_text(json.dumps(raw), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(renderer.main([str(evidence), "--output-dir", str(output)]), 0)
            saved = json.loads((output / "map.json").read_text(encoding="utf-8"))
            page = (output / "untangle.html").read_text(encoding="utf-8")
            self.assertEqual(tuple(knot["category"] for knot in saved["knots"]), categories)
            self.assertEqual(renderer.validate_manifest(saved), saved)
            for category in categories:
                self.assertIn(f"<b>Category:</b> {category}", page)

        raw["knots"][0]["category"] = "unknown-category"
        with self.assertRaisesRegex(renderer.InputError, r"knots\[0\]\.category must be one of"):
            renderer.validate_manifest(raw)

    def test_xml_forbidden_characters_are_rejected_but_unicode_is_preserved(self):
        for character in ("\uFFFE", "\uFFFF"):
            with self.subTest(codepoint=f"U+{ord(character):04X}"):
                raw = manifest()
                raw["title"] = f"Fixture {character}"
                with self.assertRaisesRegex(renderer.InputError, "XML 1.0"):
                    renderer.validate_manifest(raw)

        raw = manifest()
        raw["title"] = "Crème 東京 🧭"
        data = renderer.validate_manifest(raw)
        svg = renderer.render_svg(data)
        self.assertIn("Crème 東京 🧭", svg)
        ET.fromstring(svg)

    def test_manifest_size_limit_uses_a_bounded_stream_read(self):
        class GuardedStream:
            def __init__(self):
                self.requested_size = None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self, size=-1):
                self.requested_size = size
                if size < 0 or size > renderer.MAX_INPUT_BYTES + 1:
                    raise AssertionError("manifest read was not bounded")
                return b"x" * size

        stream = GuardedStream()
        with mock.patch.object(Path, "open", return_value=stream):
            with self.assertRaisesRegex(renderer.InputError, "size limit"):
                renderer._load_manifest(Path("oversized.json"))
        self.assertEqual(stream.requested_size, renderer.MAX_INPUT_BYTES + 1)

    def test_fixed_knot_badges_match_before_after_status(self):
        raw = manifest()
        raw["after"] = {**raw["before"], "revision": "fixture-after"}
        raw["knots"] = [
            {
                "id": 12,
                "category": "empty-wrapper",
                "severity": "high",
                "title": "Shared parser extracted",
                "features": ["feature"],
                "locations": [{"path": "source/module0.ext", "line": 1}],
                "evidence": "Two callers carried the same parsing behavior.",
                "remedy": "Use the shared parser.",
                "status": "fixed",
                "verification": [
                    {
                        "kind": "tests",
                        "command": "python -m unittest discover -s tests",
                        "result": "pass",
                    },
                    {"kind": "build", "command": "bun run check", "result": "pass"},
                ],
            },
            {
                "id": 13,
                "category": "stale-workaround",
                "severity": "medium",
                "title": "Legacy fallback remains",
                "features": ["feature"],
                "locations": [{"path": "source/module0.ext", "line": 2}],
                "evidence": "The fallback still obscures the active path.",
                "remedy": "Remove it after confirming callers.",
                "status": "open",
                "verification": [],
            },
        ]

        data = renderer.validate_manifest(raw)
        self.assertEqual(data["after"]["revision"], "fixture-after")
        svg = renderer.render_svg(data)
        page = renderer.render_html(data, svg)
        svg_namespace = "{http://www.w3.org/2000/svg}"
        svg_root = ET.fromstring(svg)

        def panel_named(name):
            return next(
                element
                for element in svg_root.iter()
                if element.tag == f"{svg_namespace}g"
                and element.get("class") == "snapshot-panel"
                and element.get("aria-label") == name
            )

        def panel_badge_fills(panel):
            badge = next(
                element
                for element in panel.iter()
                if element.tag == f"{svg_namespace}g"
                and element.get("class") == "svg-knot-badge"
                and element.get("data-knot-ids") == "12 13"
            )
            return [
                element.get("fill")
                for element in badge
                if element.tag == f"{svg_namespace}rect"
            ]

        before_panel = panel_named("Before · observed baseline snapshot")
        after_panel = panel_named("After · observed final state snapshot")
        self.assertEqual(panel_badge_fills(before_panel), ["#d94a57", "#d94a57"])
        self.assertEqual(panel_badge_fills(after_panel), ["#278355", "#d94a57"])

        summary_badges = {}
        for element in svg_root.iter():
            if element.tag != f"{svg_namespace}g" or element.get("class") != "svg-knot-badge":
                continue
            rect = next(
                (child for child in element if child.tag == f"{svg_namespace}rect"),
                None,
            )
            if rect is not None and rect.get("y") == "682":
                summary_badges[element.get("data-knot-ids")] = rect.get("fill")
        self.assertEqual(summary_badges, {"12": "#278355", "13": "#d94a57"})

        self.assertIn('<span class="knot-badge resolved">#12</span>', page)
        self.assertIn('<span class="knot-badge unresolved">#13</span>', page)
        self.assertIn(
            ".knot-badge{display:inline-flex;min-width:37px;height:25px;"
            "align-items:center;justify-content:center;border-radius:6px;background:#c93e4b;",
            page,
        )
        self.assertIn(".knot-badge.resolved{background:#278355;border:1px solid #50c78b;color:#fff}", page)
        self.assertIn(
            "red marks unresolved knots and green marks fixed knots in the after view. "
            "Baseline badges remain red to show the earlier unresolved state.",
            page,
        )

    def test_unconnected_grouped_files_have_searchable_records(self):
        data = renderer.validate_manifest(manifest())
        page = renderer.render_html(data, renderer.render_svg(data))
        parsed = FileRecords()
        parsed.feed(page)
        self.assertEqual(len(parsed.records), 19)
        for path in data["before"]["files"]:
            matches = [record for record in parsed.records if record["attributes"].get("data-file-path") == path]
            self.assertEqual(len(matches), 1, path)
            self.assertIn(path, matches[0]["text"])
        unconnected = parsed.records[-1]
        self.assertIn("No supplied proven feature/file pair", unconnected["text"])
        self.assertIn("source/", unconnected["text"])
        self.assertEqual(page.count('class="edge-record"'), 1)

    def test_inventory_keeps_snapshot_identity(self):
        raw = manifest()
        raw["after"] = {**raw["before"], "revision": "fixture-after", "edges": []}
        data = renderer.validate_manifest(raw)
        parsed = FileRecords()
        parsed.feed(renderer.render_html(data, renderer.render_svg(data)))
        self.assertEqual(len(parsed.records), 38)
        self.assertEqual({r["attributes"]["data-snapshot"] for r in parsed.records}, {"before", "after"})

    def test_fresh_output_without_hard_links(self):
        with TemporaryFixture() as directory:
            root = Path(directory)
            targets = {name: root / name for name in renderer.OUTPUT_NAMES}
            artifacts = {name: f"new {name}" for name in targets}
            original_stage = renderer._stage_file
            original_copy = renderer.shutil.copyfileobj
            staged_modes = []

            def stage_with_distinctive_mode(output_dir, content):
                path = original_stage(output_dir, content)
                path.chmod(0o640)
                staged_modes.append(stat.S_IMODE(path.stat().st_mode))
                return path

            def copy_with_source_permissions(origin, destination):
                if hasattr(renderer.os, "fchmod"):
                    self.assertEqual(
                        stat.S_IMODE(renderer.os.fstat(destination.fileno()).st_mode),
                        stat.S_IMODE(renderer.os.fstat(origin.fileno()).st_mode),
                    )
                return original_copy(origin, destination)

            with (
                mock.patch.object(renderer.os, "link", side_effect=OSError(errno.EOPNOTSUPP, "unsupported")),
                mock.patch.object(renderer, "_stage_file", side_effect=stage_with_distinctive_mode),
                mock.patch.object(renderer.shutil, "copyfileobj", side_effect=copy_with_source_permissions),
            ):
                renderer._write_outputs(root, targets, artifacts, False)
            self.assertEqual({name: path.read_text() for name, path in targets.items()}, artifacts)
            self.assertEqual([stat.S_IMODE(targets[name].stat().st_mode) for name in targets], staged_modes)

    def test_no_clobber_preserves_existing_outputs(self):
        with TemporaryFixture() as directory:
            root = Path(directory)
            targets = {name: root / name for name in renderer.OUTPUT_NAMES}
            targets["comparison.svg"].write_text("keep", encoding="utf-8")
            with self.assertRaises(renderer.InputError):
                renderer._write_outputs(root, targets, dict.fromkeys(targets, "new"), False)
            self.assertEqual(targets["comparison.svg"].read_text(), "keep")
            self.assertFalse(targets["untangle.html"].exists())

    def test_failed_copy_fallback_restores_without_hard_links(self):
        with TemporaryFixture() as directory:
            root = Path(directory)
            targets = {name: root / name for name in renderer.OUTPUT_NAMES}
            old = {name: f"old {name}" for name in targets}
            for name, path in targets.items():
                path.write_text(old[name], encoding="utf-8")
            original_copy = renderer._copy_exclusive
            calls = 0

            def fail_second_install(source, target):
                nonlocal calls
                if source.name.startswith(".untangle-stage-"):
                    calls += 1
                    if calls == 2:
                        raise OSError(errno.EIO, "copy fixture failure")
                return original_copy(source, target)

            with (
                mock.patch.object(renderer.os, "link", side_effect=OSError(errno.EOPNOTSUPP, "unsupported")),
                mock.patch.object(renderer, "_copy_exclusive", side_effect=fail_second_install),
                self.assertRaises(renderer.InputError),
            ):
                renderer._write_outputs(root, targets, dict.fromkeys(targets, "new"), True)
            self.assertEqual({name: path.read_text() for name, path in targets.items()}, old)
            self.assertFalse(list(root.glob(".untangle-backup-*")))

    def test_overwrite_rollback_preserves_readonly_file_metadata(self):
        with TemporaryFixture() as directory:
            root = Path(directory)
            targets = {name: root / name for name in renderer.OUTPUT_NAMES}
            old = {name: f"old {name}" for name in targets}
            for name, path in targets.items():
                path.write_text(old[name], encoding="utf-8")
            readonly = targets["comparison.svg"]
            readonly.chmod(stat.S_IREAD)
            original_mode = stat.S_IMODE(readonly.stat().st_mode)

            with mock.patch.object(renderer, "_publish_no_clobber", side_effect=OSError(errno.EIO, "fixture failure")):
                with self.assertRaises(renderer.InputError):
                    renderer._write_outputs(root, targets, dict.fromkeys(targets, "new"), True)

            self.assertEqual({name: path.read_text() for name, path in targets.items()}, old)
            self.assertEqual(stat.S_IMODE(readonly.stat().st_mode), original_mode)
            self.assertFalse(list(root.glob(".untangle-backup-*")))

    def test_restore_fallback_preserves_metadata_without_hard_links(self):
        with TemporaryFixture() as directory:
            root = Path(directory)
            backup = root / ".untangle-backup-comparison.svg-test.tmp"
            target = root / "comparison.svg"
            backup.write_text("old comparison", encoding="utf-8")
            backup.chmod(0o640)
            original_mode = stat.S_IMODE(backup.stat().st_mode)

            with (
                mock.patch.object(renderer.os, "name", "posix"),
                mock.patch.object(renderer.os, "link", side_effect=OSError(errno.EOPNOTSUPP, "unsupported")),
            ):
                renderer._restore_backup(backup, target)

            self.assertEqual(target.read_text(encoding="utf-8"), "old comparison")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), original_mode)
            self.assertFalse(backup.exists())

    def test_restore_fallback_never_replaces_a_concurrent_target(self):
        with TemporaryFixture() as directory:
            root = Path(directory)
            backup = root / ".untangle-backup-comparison.svg-test.tmp"
            target = root / "comparison.svg"
            backup.write_text("old comparison", encoding="utf-8")
            target.write_text("concurrent edit", encoding="utf-8")

            with (
                mock.patch.object(renderer.os, "name", "posix"),
                mock.patch.object(renderer.os, "link", side_effect=OSError(errno.EOPNOTSUPP, "unsupported")),
                self.assertRaises(FileExistsError),
            ):
                renderer._restore_backup(backup, target)

            self.assertEqual(target.read_text(encoding="utf-8"), "concurrent edit")
            self.assertEqual(backup.read_text(encoding="utf-8"), "old comparison")

    def test_enospc_publication_rollback_restores_without_copying_backup_data(self):
        with TemporaryFixture() as directory:
            root = Path(directory)
            targets = {name: root / name for name in renderer.OUTPUT_NAMES}
            old = {name: f"old {name}" for name in targets}
            for name, path in targets.items():
                path.write_text(old[name], encoding="utf-8")

            with (
                mock.patch.object(renderer, "_publish_no_clobber", side_effect=OSError(errno.ENOSPC, "full fixture")),
                mock.patch.object(renderer, "_copy_exclusive", side_effect=AssertionError("rollback recopied backup data")),
                self.assertRaises(renderer.InputError),
            ):
                renderer._write_outputs(root, targets, dict.fromkeys(targets, "new"), True)

            self.assertEqual({name: path.read_text() for name, path in targets.items()}, old)
            self.assertFalse(list(root.glob(".untangle-backup-*")))

    def test_partial_copy_failure_removes_only_its_reserved_file(self):
        with TemporaryFixture() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            source.write_bytes(b"original")

            def short_write(origin, destination):
                destination.write(b"partial")
                raise OSError(errno.ENOSPC, "full fixture")

            with mock.patch.object(renderer.shutil, "copyfileobj", side_effect=short_write), self.assertRaises(OSError):
                renderer._copy_exclusive(source, target)
            self.assertFalse(target.exists())
            self.assertEqual(source.read_bytes(), b"original")

    def test_cancellation_preserves_concurrent_edit_and_reports_recovery(self):
        with TemporaryFixture() as directory:
            root = Path(directory)
            targets = {name: root / name for name in renderer.OUTPUT_NAMES}
            for name, path in targets.items():
                path.write_text(f"old {name}", encoding="utf-8")
            original_link = renderer.os.link
            calls = 0

            def concurrent_edit_then_cancel(source, target):
                nonlocal calls
                calls += 1
                if calls == 2:
                    targets["untangle.html"].write_text("concurrent edit", encoding="utf-8")
                    raise KeyboardInterrupt()
                return original_link(source, target)

            message = io.StringIO()
            with (
                mock.patch.object(renderer.os, "link", side_effect=concurrent_edit_then_cancel),
                mock.patch.object(renderer.sys, "stderr", message),
                self.assertRaises(KeyboardInterrupt),
            ):
                renderer._write_outputs(root, targets, dict.fromkeys(targets, "new"), True)
            self.assertEqual(targets["untangle.html"].read_text(), "concurrent edit")
            for name in ("comparison.svg", "map.json"):
                self.assertEqual(targets[name].read_text(), f"old {name}")
            backups = list(root.glob(".untangle-backup-untangle.html-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), "old untangle.html")
            self.assertIn(str(backups[0]), message.getvalue())

    def test_cancellation_during_backup_disposal_preserves_published_set(self):
        with TemporaryFixture() as directory:
            root = Path(directory)
            targets = {name: root / name for name in renderer.OUTPUT_NAMES}
            for name, path in targets.items():
                path.write_text(f"old {name}", encoding="utf-8")
            keep = root / "unrelated.txt"
            keep.write_text("untouched", encoding="utf-8")
            original_unlink = Path.unlink
            interrupt_sent = False

            def interrupt_second_backup(path, *args, **kwargs):
                nonlocal interrupt_sent
                if not interrupt_sent and path.name.startswith(".untangle-backup-comparison.svg-") and path.stat().st_size:
                    interrupt_sent = True
                    raise KeyboardInterrupt()
                return original_unlink(path, *args, **kwargs)

            message = io.StringIO()
            with (
                mock.patch.object(Path, "unlink", new=interrupt_second_backup),
                mock.patch.object(renderer.sys, "stderr", message),
                self.assertRaises(KeyboardInterrupt),
            ):
                renderer._write_outputs(root, targets, dict.fromkeys(targets, "new"), True)
            self.assertTrue(interrupt_sent)
            self.assertEqual({name: path.read_text() for name, path in targets.items()}, dict.fromkeys(targets, "new"))
            self.assertEqual(keep.read_text(), "untouched")
            backups = list(root.glob(".untangle-backup-*"))
            self.assertEqual(len(backups), 2)
            for backup in backups:
                self.assertIn(str(backup), message.getvalue())
            self.assertIn("outputs published", message.getvalue())

    def test_overwrite_failure_and_cancellation_restore_originals(self):
        for failure in (OSError(errno.EIO, "fixture failure"), KeyboardInterrupt()):
            for fail_at in (1, 2):
                with self.subTest(failure=type(failure).__name__, fail_at=fail_at), TemporaryFixture() as directory:
                    root = Path(directory)
                    targets = {name: root / name for name in renderer.OUTPUT_NAMES}
                    old = {name: f"old {name}" for name in targets}
                    for name, path in targets.items():
                        path.write_text(old[name], encoding="utf-8")
                    keep = root / "unrelated.txt"
                    keep.write_text("untouched", encoding="utf-8")
                    original_link = renderer.os.link
                    calls = 0

                    def fail_publication(source, target, failure=failure, fail_at=fail_at, original_link=original_link):
                        nonlocal calls
                        calls += 1
                        if calls == fail_at:
                            raise failure
                        return original_link(source, target)

                    expected = KeyboardInterrupt if isinstance(failure, KeyboardInterrupt) else renderer.InputError
                    with mock.patch.object(renderer.os, "link", side_effect=fail_publication), self.assertRaises(expected):
                        renderer._write_outputs(root, targets, dict.fromkeys(targets, "new"), True)
                    self.assertEqual({name: path.read_text() for name, path in targets.items()}, old)
                    self.assertEqual(keep.read_text(), "untouched")
                    self.assertFalse(list(root.glob(".untangle-backup-*")))


if __name__ == "__main__":
    unittest.main()
