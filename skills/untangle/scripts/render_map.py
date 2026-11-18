#!/usr/bin/env python3
"""Render a validated Untangle v1 evidence manifest without external packages."""

from __future__ import annotations

import argparse
import contextlib
import difflib
import errno
import html
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import textwrap
from collections import defaultdict
from pathlib import Path
from typing import Any

OUTPUT_NAMES = ("untangle.html", "comparison.svg", "map.json")
FEATURE_COLORS = (
    "#4cc9f0", "#f4a261", "#a78bfa", "#34d399", "#f472b6", "#facc15",
    "#60a5fa", "#fb7185", "#2dd4bf", "#c084fc", "#a3e635", "#f97316",
    "#38bdf8", "#e879f9", "#4ade80", "#fda4af", "#818cf8", "#fbbf24",
)
KNOT_CATEGORIES = {
    "leaky-abstraction", "drifted-duplication", "stale-workaround", "empty-wrapper",
    "dependency-cycle", "mixed-responsibilities",
}
SEVERITIES = {"high", "medium", "low"}
STATUSES = {"open", "fixed", "rolled-back", "blocked", "deferred"}
VERIFICATION_KINDS = {"tests", "build", "other"}
VERIFICATION_RESULTS = {"pass", "fail", "blocked", "not-applicable"}
EDGE_KINDS = {"direct", "transitive", "configured", "observed"}
MAX_INPUT_BYTES = 2_000_000
MAX_TEXT = 4_000
MAX_FEATURES = 18
MAX_KNOTS = 250
MAX_FILES = 2_000
MAX_EDGES = 4_000
MAX_EVIDENCE_PER_EDGE = 40
MAX_LOCATIONS_PER_KNOT = 100
MAX_VERIFICATIONS_PER_KNOT = 100


class InputError(ValueError):
    """A manifest or output path does not meet the renderer contract."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "input_error",
        context: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = context
        self.hint = hint


class SafetyError(InputError):
    """An output path or overwrite request would violate a safety gate."""

    def __init__(self, message: str, *, context: str | None = None, hint: str | None = None) -> None:
        super().__init__(message, code="safety_error", context=context, hint=hint)


class FilesystemError(InputError):
    """A filesystem operation could not complete."""

    def __init__(self, message: str, *, context: str | None = None, hint: str | None = None) -> None:
        super().__init__(message, code="filesystem_error", context=context, hint=hint)


class _ArgumentFailure(Exception):
    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


class _ParserExit(Exception):
    def __init__(self, status: int, message: str | None = None) -> None:
        super().__init__(message or "")
        self.status = status
        self.message = message or ""


class _RendererArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _ArgumentFailure(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise _ParserExit(status, message)


CLI_RESULT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Untangle renderer CLI result",
    "oneOf": [
        {
            "type": "object",
            "required": ["schema_version", "ok", "mode", "result"],
            "additionalProperties": False,
            "properties": {
                "schema_version": {"const": 1},
                "ok": {"const": True},
                "mode": {"const": "render"},
                "result": {"$ref": "#/$defs/output-result"},
            },
        },
        {
            "type": "object",
            "required": ["schema_version", "ok", "mode", "result"],
            "additionalProperties": False,
            "properties": {
                "schema_version": {"const": 1},
                "ok": {"const": True},
                "mode": {"const": "dry-run"},
                "result": {"$ref": "#/$defs/output-result"},
            },
        },
        {
            "type": "object",
            "required": ["schema_version", "ok", "mode", "result"],
            "additionalProperties": False,
            "properties": {
                "schema_version": {"const": 1},
                "ok": {"const": True},
                "mode": {"const": "check"},
                "result": {"$ref": "#/$defs/check-result"},
            },
        },
        {
            "type": "object",
            "required": ["schema_version", "ok", "mode", "error"],
            "additionalProperties": False,
            "properties": {
                "schema_version": {"const": 1},
                "ok": {"const": False},
                "mode": {"const": "error"},
                "error": {"$ref": "#/$defs/error"},
            },
        },
    ],
    "$defs": {
        "output": {
            "type": "object",
            "required": ["path", "action"],
            "additionalProperties": False,
            "properties": {
                "path": {"type": "string"},
                "action": {"enum": ["create", "replace"]},
            },
        },
        "output-result": {
            "type": "object",
            "required": ["input", "outputs"],
            "additionalProperties": False,
            "properties": {
                "input": {"type": "string"},
                "outputs": {"type": "array", "items": {"$ref": "#/$defs/output"}},
            },
        },
        "check-result": {
            "type": "object",
            "required": ["input", "valid"],
            "additionalProperties": False,
            "properties": {
                "input": {"type": "string"},
                "valid": {"const": True},
            },
        },
        "error": {
            "type": "object",
            "required": ["code", "message", "context", "hint"],
            "additionalProperties": False,
            "properties": {
                "code": {"enum": ["input_error", "argument_error", "safety_error", "filesystem_error", "cancelled"]},
                "message": {"type": "string"},
                "context": {"type": ["string", "null"]},
                "hint": {"type": ["string", "null"]},
            },
        },
    },
}


def _object(value: Any, where: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{where} must be an object")
    missing = fields - value.keys()
    unknown = value.keys() - fields
    if missing:
        raise InputError(f"{where} is missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise InputError(f"{where} has unknown field(s): {', '.join(sorted(unknown))}")
    return value


def _items(value: Any, where: str, maximum: int, minimum: int = 0) -> list[Any]:
    if not isinstance(value, list):
        raise InputError(f"{where} must be an array")
    if len(value) < minimum:
        raise InputError(f"{where} must contain at least {minimum} item(s)")
    if len(value) > maximum:
        if where == "features":
            raise InputError(f"{where} exceeds the limit of {maximum}; map a smaller subsystem and disclose the scope")
        raise InputError(f"{where} exceeds the limit of {maximum} items")
    return value


def _string(value: Any, where: str, maximum: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{where} must be a non-empty string")
    if len(value) > maximum:
        raise InputError(f"{where} exceeds the {maximum}-character limit")
    if any(ord(ch) < 0x20 and ch not in "\n\r\t" for ch in value):
        raise InputError(f"{where} contains a control character")
    if any(ord(ch) in {0xFFFE, 0xFFFF} for ch in value):
        raise InputError(f"{where} contains a character forbidden by XML 1.0")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InputError(f"{where} contains invalid Unicode") from exc
    return value


def _positive_int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InputError(f"{where} must be a positive integer")
    return value


def _enum(value: Any, where: str, choices: set[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise InputError(f"{where} must be one of: {', '.join(sorted(choices))}")
    return value


def _repo_path(value: Any, where: str) -> str:
    path = _string(value, where, 600)
    if "\\" in path or path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise InputError(f"{where} must be a repo-relative POSIX path")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise InputError(f"{where} must not contain empty, '.' or '..' path segments")
    if any(ord(ch) < 0x20 for ch in path):
        raise InputError(f"{where} contains a control character")
    return path


def _duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _validate_location(raw: Any, where: str) -> dict[str, Any]:
    item = _object(raw, where, {"path", "line"})
    return {
        "path": _repo_path(item["path"], f"{where}.path"),
        "line": _positive_int(item["line"], f"{where}.line"),
    }


def _validate_snapshot(raw: Any, where: str, feature_ids: set[str]) -> dict[str, Any]:
    item = _object(raw, where, {"revision", "coverage", "files", "edges"})
    revision = _string(item["revision"], f"{where}.revision", 300)
    coverage = _string(item["coverage"], f"{where}.coverage", 2_000)
    raw_files = _items(item["files"], f"{where}.files", MAX_FILES)
    files: list[str] = []
    file_set: set[str] = set()
    for index, raw_file in enumerate(raw_files):
        file_path = _repo_path(raw_file, f"{where}.files[{index}]")
        if file_path in file_set:
            raise InputError(f"{where}.files contains duplicate path: {file_path}")
        file_set.add(file_path)
        files.append(file_path)

    raw_edges = _items(item["edges"], f"{where}.edges", MAX_EDGES)
    edges: list[dict[str, Any]] = []
    pairs: set[tuple[str, str]] = set()
    for index, raw_edge in enumerate(raw_edges):
        edge_where = f"{where}.edges[{index}]"
        edge = _object(raw_edge, edge_where, {"feature", "file", "evidence"})
        feature = _string(edge["feature"], f"{edge_where}.feature", 200)
        file_path = _repo_path(edge["file"], f"{edge_where}.file")
        if feature not in feature_ids:
            raise InputError(f"{edge_where}.feature references unknown feature: {feature}")
        if file_path not in file_set:
            raise InputError(f"{edge_where}.file is not listed in {where}.files: {file_path}")
        pair = (feature, file_path)
        if pair in pairs:
            raise InputError(f"{where}.edges repeats feature/file pair: {feature} -> {file_path}")
        pairs.add(pair)
        raw_evidence = _items(edge["evidence"], f"{edge_where}.evidence", MAX_EVIDENCE_PER_EDGE, 1)
        evidence: list[dict[str, Any]] = []
        for evidence_index, raw_record in enumerate(raw_evidence):
            record_where = f"{edge_where}.evidence[{evidence_index}]"
            record = _object(raw_record, record_where, {"path", "line", "note", "kind"})
            evidence.append({
                "path": _repo_path(record["path"], f"{record_where}.path"),
                "line": _positive_int(record["line"], f"{record_where}.line"),
                "note": _string(record["note"], f"{record_where}.note", 2_000),
                "kind": _enum(record["kind"], f"{record_where}.kind", EDGE_KINDS),
            })
        edges.append({"feature": feature, "file": file_path, "evidence": evidence})

    return {"revision": revision, "coverage": coverage, "files": files, "edges": edges}


def _validate_comparison(raw: Any, where: str, before: dict[str, Any], after: dict[str, Any] | None) -> dict[str, Any]:
    if after is None:
        raise InputError(f"{where} requires an actual after snapshot; do not present a proposal as completed work")
    item = _object(raw, where, {"before", "after", "benefit", "preserved"})
    result: dict[str, Any] = {
        "benefit": _string(item["benefit"], f"{where}.benefit", 700),
        "preserved": _string(item["preserved"], f"{where}.preserved", 700),
    }
    for phase, snapshot in (("before", before), ("after", after)):
        phase_where = f"{where}.{phase}"
        fields = {"summary", "snippets"}
        if isinstance(item[phase], dict) and "paths" in item[phase]:
            fields.add("paths")
        side = _object(item[phase], phase_where, fields)
        snippets = []
        for index, raw_snippet in enumerate(_items(side["snippets"], f"{phase_where}.snippets", 6, 1)):
            snippet_where = f"{phase_where}.snippets[{index}]"
            snippet = _object(raw_snippet, snippet_where, {"path", "line", "code"})
            source = _repo_path(snippet["path"], f"{snippet_where}.path")
            if source not in snapshot["files"]:
                raise InputError(f"{snippet_where}.path is not listed in {phase}.files: {source}")
            code = _string(snippet["code"], f"{snippet_where}.code", 1_000)
            if len(code.splitlines()) > 12:
                raise InputError(f"{snippet_where}.code exceeds the limit of 12 lines")
            snippets.append({"path": source, "line": _positive_int(snippet["line"], f"{snippet_where}.line"), "code": code})
        result[phase] = {"summary": _string(side["summary"], f"{phase_where}.summary", 400), "snippets": snippets}
        if "paths" in side:
            paths = []
            ids: set[str] = set()
            for index, raw_path in enumerate(_items(side["paths"], f"{phase_where}.paths", 4, 1)):
                path_where = f"{phase_where}.paths[{index}]"
                path_fields = {"id", "label", "from", "to", "value"}
                if isinstance(raw_path, dict) and "via" in raw_path:
                    path_fields.add("via")
                path = _object(raw_path, path_where, path_fields)
                path_id = _string(path["id"], f"{path_where}.id", 80)
                if path_id in ids:
                    raise InputError(f"{phase_where}.paths contains duplicate id: {path_id}")
                ids.add(path_id)
                record: dict[str, Any] = {
                    "id": path_id,
                    "label": _string(path["label"], f"{path_where}.label", 120),
                    "value": _string(path["value"], f"{path_where}.value", 100),
                }
                def endpoint_record(raw_node: Any, node_where: str) -> dict[str, Any]:
                    node = _object(raw_node, node_where, {"snippet", "label"})
                    reference = _positive_int(node["snippet"], f"{node_where}.snippet")
                    if reference > len(snippets):
                        raise InputError(f"{node_where}.snippet references a missing source excerpt")
                    return {"snippet": reference, "label": _string(node["label"], f"{node_where}.label", 120)}
                for endpoint in ("from", "to"):
                    record[endpoint] = endpoint_record(path[endpoint], f"{path_where}.{endpoint}")
                if "via" in path:
                    record["via"] = [endpoint_record(node, f"{path_where}.via[{index}]")
                                     for index, node in enumerate(_items(path["via"], f"{path_where}.via", 2, 1))]
                paths.append(record)
            result[phase]["paths"] = paths
    if ("paths" in result["before"]) != ("paths" in result["after"]):
        raise InputError(f"{where} must supply paths in both before and after, or neither")
    if "paths" in result["before"]:
        before_paths = [(path["id"], path["label"]) for path in result["before"]["paths"]]
        after_paths = [(path["id"], path["label"]) for path in result["after"]["paths"]]
        if before_paths != after_paths:
            raise InputError(f"{where} path IDs, labels and order must match across snapshots")
        for index, (before_path, after_path) in enumerate(zip(result["before"]["paths"], result["after"]["paths"], strict=True)):
            if before_path.get("via") or after_path.get("via"):
                for phase, path in (("before", before_path), ("after", after_path)):
                    sources = result[phase]["snippets"]
                    owners = [sources[node["snippet"] - 1]["path"] for node in [path["from"], *path.get("via", []), path["to"]]]
                    if len(owners) != len(set(owners)):
                        raise InputError(f"{where}.{phase}.paths[{index}] must describe distinct source owners when either phase supplies via")
    return result


def validate_manifest(raw: Any) -> dict[str, Any]:
    top = _object(raw, "manifest", {"schema_version", "title", "scope", "features", "knots", "before", "after"})
    version = top["schema_version"]
    if isinstance(version, bool) or version != 1 or not isinstance(version, int):
        raise InputError("schema_version must be the integer 1")

    title = _string(top["title"], "title", 300)
    scope = _string(top["scope"], "scope", 2_000)
    raw_features = _items(top["features"], "features", MAX_FEATURES, 1)
    features: list[dict[str, str]] = []
    feature_ids: set[str] = set()
    for index, raw_feature in enumerate(raw_features):
        where = f"features[{index}]"
        feature = _object(raw_feature, where, {"id", "label"})
        feature_id = _string(feature["id"], f"{where}.id", 200)
        if feature_id != feature_id.strip():
            raise InputError(f"{where}.id must not have leading or trailing whitespace")
        if feature_id in feature_ids:
            raise InputError(f"features contains duplicate id: {feature_id}")
        feature_ids.add(feature_id)
        features.append({"id": feature_id, "label": _string(feature["label"], f"{where}.label", 400)})

    before = _validate_snapshot(top["before"], "before", feature_ids)
    after = None if top["after"] is None else _validate_snapshot(top["after"], "after", feature_ids)

    raw_knots = _items(top["knots"], "knots", MAX_KNOTS)
    knots: list[dict[str, Any]] = []
    knot_ids: set[int] = set()
    for index, raw_knot in enumerate(raw_knots):
        where = f"knots[{index}]"
        fields = {
            "id", "category", "severity", "title", "features", "locations", "evidence", "remedy", "status", "verification"
        }
        if isinstance(raw_knot, dict) and "comparison" in raw_knot:
            fields.add("comparison")
        knot = _object(raw_knot, where, fields)
        knot_id = _positive_int(knot["id"], f"{where}.id")
        if knot_id in knot_ids:
            raise InputError(f"knots contains duplicate id: {knot_id}")
        knot_ids.add(knot_id)

        raw_knot_features = _items(knot["features"], f"{where}.features", MAX_FEATURES, 1)
        knot_features: list[str] = []
        for feature_index, feature_value in enumerate(raw_knot_features):
            feature_id = _string(feature_value, f"{where}.features[{feature_index}]", 200)
            if feature_id not in feature_ids:
                raise InputError(f"{where}.features references unknown feature: {feature_id}")
            if feature_id in knot_features:
                raise InputError(f"{where}.features contains duplicate reference: {feature_id}")
            knot_features.append(feature_id)

        raw_locations = _items(knot["locations"], f"{where}.locations", MAX_LOCATIONS_PER_KNOT, 1)
        locations = [_validate_location(loc, f"{where}.locations[{loc_index}]") for loc_index, loc in enumerate(raw_locations)]

        raw_verifications = _items(knot["verification"], f"{where}.verification", MAX_VERIFICATIONS_PER_KNOT)
        verifications: list[dict[str, str]] = []
        for check_index, raw_check in enumerate(raw_verifications):
            check_where = f"{where}.verification[{check_index}]"
            if not isinstance(raw_check, dict):
                raise InputError(f"{check_where} must be an object")
            verification_fields = {"kind", "command", "result"}
            if "note" in raw_check:
                verification_fields.add("note")
            check = _object(raw_check, check_where, verification_fields)
            record = {
                "kind": _enum(check["kind"], f"{check_where}.kind", VERIFICATION_KINDS),
                "command": _string(check["command"], f"{check_where}.command", 1_000),
                "result": _enum(check["result"], f"{check_where}.result", VERIFICATION_RESULTS),
            }
            if "note" in check:
                record["note"] = _string(check["note"], f"{check_where}.note", 2_000)
            verifications.append(record)

        knots.append({
            "id": knot_id,
            "category": _enum(knot["category"], f"{where}.category", KNOT_CATEGORIES),
            "severity": _enum(knot["severity"], f"{where}.severity", SEVERITIES),
            "title": _string(knot["title"], f"{where}.title", 500),
            "features": knot_features,
            "locations": locations,
            "evidence": _string(knot["evidence"], f"{where}.evidence", 4_000),
            "remedy": _string(knot["remedy"], f"{where}.remedy", 4_000),
            "status": _enum(knot["status"], f"{where}.status", STATUSES),
            "verification": verifications,
        })
        if "comparison" in knot:
            knots[-1]["comparison"] = _validate_comparison(knot["comparison"], f"{where}.comparison", before, after)

    for knot in knots:
        if knot["status"] != "fixed":
            continue
        if after is None:
            raise InputError(f"fixed knot #{knot['id']} requires an actual after snapshot")
        tests = [entry for entry in knot["verification"] if entry["kind"] == "tests"]
        builds = [entry for entry in knot["verification"] if entry["kind"] == "build"]
        if not tests or not all(
            entry["result"] == "pass"
            or (entry["result"] == "not-applicable" and "no tests" in entry.get("note", "").lower())
            for entry in tests
        ):
            raise InputError(f"fixed knot #{knot['id']} requires passing tests or a not-applicable test record noting 'no tests'")
        if not builds or not all(entry["result"] == "pass" for entry in builds):
            raise InputError(f"fixed knot #{knot['id']} requires a passing build record; build not-applicable is not accepted")
        if any(entry["result"] in {"fail", "blocked"} for entry in knot["verification"]):
            raise InputError(f"fixed knot #{knot['id']} cannot include a failed or blocked verification record")

    return {
        "schema_version": 1,
        "title": title,
        "scope": scope,
        "features": features,
        "knots": knots,
        "before": before,
        "after": after,
    }


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _truncate(value: str, limit: int) -> str:
    flat = " ".join(value.split())
    if len(flat) <= limit:
        return flat
    return flat[: max(0, limit - 1)].rstrip() + "…"


def _file_label(path: str, limit: int) -> str:
    if len(path) <= limit:
        return path
    # Long sibling paths can share a truncated directory prefix. Show the
    # filename first; the node title and inventory retain the exact full path.
    return _truncate(path.rsplit("/", 1)[-1], limit)


def _feature_indices(features: list[dict[str, str]]) -> dict[str, int]:
    return {feature["id"]: index for index, feature in enumerate(features)}


def _union_groups(before: dict[str, Any], after: dict[str, Any] | None) -> tuple[list[dict[str, Any]], bool]:
    """Choose one shared file/folder grouping and order for both panels."""
    ordered: list[str] = []
    seen: set[str] = set()
    for snapshot in (before, after):
        if snapshot is None:
            continue
        for path in snapshot["files"]:
            if path not in seen:
                seen.add(path)
                ordered.append(path)
    grouped = len(ordered) > 18
    if not grouped:
        return ([{"key": path, "label": path, "members": [path]} for path in ordered], False)

    by_parent: dict[str, list[str]] = defaultdict(list)
    for path in ordered:
        parent = path.rpartition("/")[0] or "(repository root)"
        by_parent[parent].append(path)
    directory_keys = list(by_parent)
    if len(directory_keys) > 18:
        by_top: dict[str, list[str]] = defaultdict(list)
        for path in ordered:
            parts = path.split("/")
            key = parts[0] if len(parts) > 1 else "(repository root)"
            by_top[key].append(path)
        directory_keys = list(by_top)
        by_parent = by_top
        suffix = "/…" if any("/" in path for path in ordered) else ""
        labels = {key: ("repository root" if key == "(repository root)" else key + suffix) for key in directory_keys}
    else:
        labels = {key: ("repository root" if key == "(repository root)" else key + "/") for key in directory_keys}

    if len(directory_keys) > 18:
        keep = directory_keys[:17]
        overflow = directory_keys[17:]
        groups = [{"key": "dir:" + key, "label": labels[key], "members": by_parent[key]} for key in keep]
        overflow_members = [path for key in overflow for path in by_parent[key]]
        groups.append({
            "key": "other-directories",
            "label": f"Other directories ({len(overflow)} dirs)",
            "members": overflow_members,
        })
    else:
        groups = [{"key": "dir:" + key, "label": labels[key], "members": by_parent[key]} for key in directory_keys]
    return groups, True


def _positions(count: int, top: float, bottom: float) -> list[float]:
    if count <= 0:
        return []
    if count == 1:
        return [(top + bottom) / 2]
    step = (bottom - top) / (count - 1)
    return [top + step * index for index in range(count)]


def _svg_text(x: float, y: float, value: str, size: float = 12, color: str = "#dce6f2", weight: str = "400", extra: str = "") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" font-size="{size:g}" '
            f'font-weight="{weight}" fill="{color}" {extra}>{_escape(value)}</text>')


def _marker_span(knot_ids: set[int], large: bool) -> int:
    return min(3, len(knot_ids)) * (36 if large else 29) - 2 if knot_ids else 0


def _svg_knot_markers(knot_ids: set[int], knots: dict[int, dict[str, Any]], after: bool, x: float, y: float, large: bool = False) -> str:
    if not knot_ids:
        return ""
    priority = {"high": 0, "medium": 1, "low": 2}
    ordered = sorted(knot_ids, key=lambda knot_id: (priority[knots[knot_id]["severity"]], knot_id))
    visible = ordered[:2]
    details = []
    for knot_id in ordered:
        knot = knots[knot_id]
        locations = ", ".join(f'{loc["path"]}:{loc["line"]}' for loc in knot["locations"])
        state = knot["status"] if after else "baseline knot"
        details.append(f'#{knot_id} {knot["title"]} · {state} · baseline {locations}')
    tooltip = "; ".join(details)
    result = [f'<g class="svg-knot-badge" data-knot-ids="{" ".join(str(knot_id) for knot_id in ordered)}">',
              f'<title>{_escape(tooltip)}</title>']
    cursor = x
    badge_width, badge_height = (34, 24) if large else (27, 15)
    font_size = 14 if large else 7.5
    baseline = 5 if large else 2.7
    step = 36 if large else 29
    for knot_id in visible:
        knot = knots[knot_id]
        resolved = after and knot["status"] == "fixed"
        fill = "#278355" if resolved else "#d94a57"
        identifier = f'#{knot_id}' if len(str(knot_id)) <= (2 if large else 4) else "#…"
        result.append(f'<rect x="{cursor:.1f}" y="{y - badge_height / 2:.1f}" width="{badge_width}" height="{badge_height}" rx="4" fill="{fill}"/>')
        result.append(_svg_text(cursor + badge_width / 2, y + baseline, identifier, font_size, "#ffffff", "700", 'text-anchor="middle"'))
        cursor += step
    if len(ordered) > len(visible):
        remainder = len(ordered) - len(visible)
        result.append(f'<rect x="{cursor:.1f}" y="{y - badge_height / 2:.1f}" width="{badge_width}" height="{badge_height}" rx="4" fill="#536174"/>')
        result.append(_svg_text(cursor + badge_width / 2, y + baseline, f"+{remainder}", font_size, "#ffffff", "700", 'text-anchor="middle"'))
    result.append("</g>")
    return "".join(result)


def _render_panel(
    snapshot: dict[str, Any] | None,
    title: str,
    x: int,
    data: dict[str, Any],
    file_groups: list[dict[str, Any]],
    feature_lookup: dict[str, int],
) -> str:
    width = 780
    readable = len(file_groups) <= 8 and len(data["features"]) <= 8
    panel_y = 128
    parts = [f'<g class="snapshot-panel" aria-label="{_escape(title)} snapshot">',
             f'<rect x="{x}" y="{panel_y}" width="{width}" height="530" rx="14" fill="#0c1420" stroke="#243247"/>']
    parts.append(_svg_text(x + 18, 154, title.upper(), 13, "#97abc3", "700", 'letter-spacing="1.5"'))
    if snapshot is None:
        parts.append(_svg_text(x + 18, 181, "No final snapshot supplied · after work was not run", 14, "#c4d0de", "600"))
        parts.append(f'<rect x="{x + 26}" y="232" width="{width - 52}" height="366" rx="14" fill="#111a28" stroke="#3b4757" stroke-dasharray="7 7"/>')
        parts.append(_svg_text(x + width / 2, 390, "AFTER NOT RUN", 24, "#bac5d2", "700", 'text-anchor="middle" letter-spacing="2"'))
        parts.append(_svg_text(x + width / 2, 420, "No graph is inferred for a missing after snapshot.", 13, "#8796a8", "400", 'text-anchor="middle"'))
        parts.append(_svg_text(x + width / 2, 444, "The evidence manifest keeps after = null.", 12, "#718095", "400", 'text-anchor="middle"'))
        parts.append("</g>")
        return "".join(parts)

    parts.append(_svg_text(x + 18, 180, "Revision: " + _truncate(snapshot["revision"], 82), 11, "#dce6f2", "500"))
    parts.append(f'<title>{_escape(snapshot["revision"])}</title>')
    parts.append(_svg_text(x + 18, 201, "Coverage: " + _truncate(snapshot["coverage"], 94), 10, "#96a6ba"))
    parts.append(f'<title>{_escape(snapshot["coverage"])}</title>')
    evidence_count = sum(len(edge["evidence"]) for edge in snapshot["edges"])
    count_line = f'{len(snapshot["files"])} files · {len(snapshot["edges"])} feature/file pairs · {evidence_count} source evidence records'
    parts.append(_svg_text(x + 18, 222, count_line, 11, "#b0bed0", "600"))

    graph_top, graph_bottom = (258.0 if readable else 244.0), 624.0
    feature_ys = _positions(len(data["features"]), graph_top, graph_bottom)
    active_files = set(snapshot["files"])
    visible_group_members = [
        [path for path in group["members"] if path in active_files]
        for group in file_groups
    ]
    visible_group_ids = [index for index, members in enumerate(visible_group_members) if members]
    all_group_ys = _positions(len(file_groups), graph_top, graph_bottom)
    group_y = {index: y for index, y in enumerate(all_group_ys)}
    group_for_file = {path: index for index, group in enumerate(file_groups) for path in group["members"]}
    knot_lookup = {knot["id"]: knot for knot in data["knots"]}
    knot_file_ids: dict[int, set[int]] = defaultdict(set)
    knot_feature_fallbacks: dict[int, set[int]] = defaultdict(set)
    for knot in data["knots"]:
        affected_paths = {location["path"] for location in knot["locations"]}
        if "comparison" in knot:
            phase = "after" if title.lower().startswith("after") else "before"
            affected_paths.update(snippet["path"] for snippet in knot["comparison"][phase]["snippets"])
        for path in affected_paths:
            if path in active_files:
                knot_file_ids[group_for_file[path]].add(knot["id"])
            else:
                for feature_id in knot["features"]:
                    knot_feature_fallbacks[feature_lookup[feature_id]].add(knot["id"])

    feature_x = x + 16
    feature_w = 196 if readable else 166
    file_w = 252 if readable else 180
    file_x = x + width - file_w - 18
    pair_counts: dict[tuple[int, int], int] = defaultdict(int)
    for edge in snapshot["edges"]:
        pair_counts[(feature_lookup[edge["feature"]], group_for_file[edge["file"]])] += 1
    other = data["after"] if title.lower().startswith("before") else data["before"]
    other_pairs = {(edge["feature"], edge["file"]) for edge in other["edges"]} if other is not None else None
    changed_pairs = set() if other_pairs is None else {
        (feature_lookup[edge["feature"]], group_for_file[edge["file"]])
        for edge in snapshot["edges"] if (edge["feature"], edge["file"]) not in other_pairs
    }

    for (feature_index, group_index), count in sorted(pair_counts.items()):
        fy = feature_ys[feature_index]
        gy = group_y[group_index]
        start_x, end_x = feature_x + feature_w, file_x
        curve_x = (start_x + end_x) / 2
        color = FEATURE_COLORS[feature_index]
        changed = (feature_index, group_index) in changed_pairs
        stroke_width = (3 if changed else 1.4) + min(1.8, (count - 1) * 0.24)
        change_style = 'stroke-dasharray="8 4"' if changed else ""
        parts.append(
            f'<path class="edge" data-feature-index="{feature_index}" data-file-group-index="{group_index}" '
            f'data-edge-count="{count}" d="M {start_x} {fy:.1f} C {curve_x:.1f} {fy:.1f}, {curve_x:.1f} {gy:.1f}, {end_x} {gy:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="{stroke_width:.1f}" stroke-opacity="0.85" {change_style}/>'
        )
        if count > 1:
            parts.append(_svg_text(curve_x, (fy + gy) / 2 - 3, f"x{count}", 9, color, "700", 'text-anchor="middle"'))

    if not snapshot["edges"]:
        parts.append(_svg_text(x + width / 2, 430, "No observed feature/file pairs supplied", 12, "#7f8da0", "500", 'text-anchor="middle"'))

    for feature_index, (feature, y) in enumerate(zip(data["features"], feature_ys, strict=True)):
        color = FEATURE_COLORS[feature_index]
        label = _truncate(feature["label"], 23)
        parts.append(f'<g class="diagram-feature" data-feature-index="{feature_index}"><title>{_escape(feature["label"])}</title>')
        node_height = 48 if readable else 20
        parts.append(f'<rect x="{feature_x}" y="{y - node_height / 2:.1f}" width="{feature_w}" height="{node_height}" rx="5" fill="#152435" stroke="{color}" stroke-width="1.4"/>')
        parts.append(f'<circle cx="{feature_x + 9}" cy="{y:.1f}" r="3.2" fill="{color}"/>')
        if knot_feature_fallbacks[feature_index]:
            reserved = _marker_span(knot_feature_fallbacks[feature_index], readable)
            limit = max(5, int((feature_w - reserved - 28) / (8.25 if readable else 5.5)))
            label = _truncate(feature["label"], limit)
        if readable and not knot_feature_fallbacks[feature_index]:
            lines = textwrap.wrap(_truncate(feature["label"], 38), width=20)
            if len(lines) > 2:
                lines = [lines[0], _truncate(" ".join(lines[1:]), 20)]
            first_y = y + 5 if len(lines) == 1 else y - 3
            for line_index, line in enumerate(lines):
                parts.append(_svg_text(feature_x + 17, first_y + 18 * line_index, line, 15, "#edf4fb", "600"))
        else:
            parts.append(_svg_text(feature_x + 17, y + (5 if readable else 3.6), label, 15 if readable else 10, "#edf4fb", "600"))
        parts.append("</g>")
        if knot_feature_fallbacks[feature_index]:
            marker_x = feature_x + feature_w - _marker_span(knot_feature_fallbacks[feature_index], readable) - 4
            parts.append(_svg_knot_markers(knot_feature_fallbacks[feature_index], knot_lookup, title.lower().startswith("after"), marker_x, y, readable))

    for group_index in visible_group_ids:
        group = file_groups[group_index]
        members = visible_group_members[group_index]
        y = group_y[group_index]
        marker_width = _marker_span(knot_file_ids[group_index], readable)
        if knot_file_ids[group_index] and len(group["members"]) == 1 and not group["key"].startswith("dir:"):
            limit = max(5, int((file_w - marker_width - 20) / (9.35 if readable else 5.2)))
            label = _file_label(members[0], limit)
        elif knot_file_ids[group_index]:
            label = f'{_truncate(group["label"], 12)} · {len(members)} file' + ("s" if len(members) != 1 else "")
        elif len(group["members"]) == 1 and not group["key"].startswith("dir:"):
            label = _file_label(members[0], 29)
        else:
            label = f'{_truncate(group["label"], 23)} · {len(members)} file' + ("s" if len(members) != 1 else "")
        parts.append(f'<g class="diagram-file" data-file-group-index="{group_index}"><title>{_escape("; ".join(members))}</title>')
        node_height = 36 if readable else 20
        parts.append(f'<rect x="{file_x}" y="{y - node_height / 2:.1f}" width="{file_w}" height="{node_height}" rx="5" fill="#111d2b" stroke="#60738b" stroke-width="1"/>')
        parts.append(_svg_text(file_x + 8, y + (6 if readable else 3.5), label, 17 if readable else 9.5, "#cfdae7", "500"))
        parts.append("</g>")
        if knot_file_ids[group_index]:
            parts.append(_svg_knot_markers(knot_file_ids[group_index], knot_lookup, title.lower().startswith("after"), file_x + file_w - marker_width - 4, y, readable))

    if len(set(path for group in file_groups for path in group["members"])) > 18:
        parts.append(_svg_text(x + 18, 645, "Folder nodes group files; counts belong to this snapshot.", 9, "#8d9db1"))
    parts.append("</g>")
    return "".join(parts)


def render_wiring_svg(data: dict[str, Any]) -> str:
    feature_lookup = _feature_indices(data["features"])
    file_groups, grouped = _union_groups(data["before"], data["after"])
    before_panel = _render_panel(data["before"], "Before · observed baseline", 16, data, file_groups, feature_lookup)
    after_panel = _render_panel(data["after"], "After · observed final state", 804, data, file_groups, feature_lookup)
    status_counts = {status: sum(knot["status"] == status for knot in data["knots"]) for status in sorted(STATUSES)}
    status_line = "Knot status: " + " · ".join(f"{status} {count}" for status, count in status_counts.items())
    parts = [
        '<svg class="comparison" xmlns="http://www.w3.org/2000/svg" width="1600" height="760" viewBox="0 0 1600 760" role="img" aria-labelledby="svg-title svg-description">',
        f'<title id="svg-title">{_escape(data["title"])} · before and after wiring map</title>',
        f'<desc id="svg-description">{_escape(data["scope"])}. Feature-to-file pairs are colored by feature. The renderer validates evidence shape and references; it does not certify code truth.</desc>',
        '<rect width="1600" height="760" rx="18" fill="#070c14"/>',
        _svg_text(24, 36, data["title"], 22, "#f2f6fb", "700"),
        _svg_text(24, 56, _truncate(data["scope"], 170), 10, "#a5b4c7", "400"),
        _svg_text(24, 75, status_line, 9, "#c2cede", "500"),
        _svg_text(22, 94, "FEATURE COLORS", 8, "#8fa2b8", "700", 'letter-spacing="1"'),
    ]
    for index, feature in enumerate(data["features"]):
        row, column = divmod(index, 9)
        base_x = 124 + column * 163
        y = 94 + row * 17
        color = FEATURE_COLORS[index]
        parts.append(f'<circle cx="{base_x + 4}" cy="{y - 2.5}" r="3.5" fill="{color}"/>')
        parts.append(_svg_text(base_x + 12, y, _truncate(feature["label"], 20), 8, "#d2dce8", "500"))
    parts.extend([
        before_panel,
        after_panel,
        _svg_text(22, 675, "NUMBERED KNOTS / red = baseline or unresolved; green = recorded fixed status", 11, "#a5b4c7", "700"),
    ])
    severity_order = {"high": 0, "medium": 1, "low": 2}
    top_knots = sorted(data["knots"], key=lambda knot: (severity_order[knot["severity"]], knot["id"]))[:3]
    if not top_knots:
        parts.append(_svg_text(22, 698, "No knots recorded in the manifest.", 10, "#a5b4c7"))
    else:
        for index, knot in enumerate(top_knots):
            base_x = 22 + index * 520
            badge_fill = "#278355" if knot["status"] == "fixed" else "#d94a57"
            parts.append(f'<g class="svg-knot-badge" data-knot-ids="{knot["id"]}"><title>{_escape(knot["title"] + " · " + knot["remedy"])}</title>')
            parts.append(f'<rect x="{base_x}" y="682" width="39" height="19" rx="5" fill="{badge_fill}"/>')
            parts.append(_svg_text(base_x + 19.5, 695.5, f'#{knot["id"]}', 9, "#ffffff", "700", 'text-anchor="middle"'))
            parts.append("</g>")
            status_color = "#78d9a1" if knot["status"] == "fixed" else "#f28c96"
            label = f'{_truncate(knot["title"], 43)} · {knot["severity"]} · {knot["status"]}'
            parts.append(_svg_text(base_x + 47, 695.5, label, 9, status_color, "600"))
            first_location = knot["locations"][0]
            lower = f'{first_location["path"]}:{first_location["line"]} · {_truncate(knot["remedy"], 58)}'
            parts.append(_svg_text(base_x + 2, 715, lower, 8, "#a5b4c7", "400"))

    if grouped:
        footer = "Folder nodes use shared before/after groups; full paths, edges and evidence remain searchable in untangle.html."
    else:
        footer = "Full paths and evidence are in untangle.html. Coverage is supplied by the manifest; this renderer does not certify code truth or completeness."
    parts.append(_svg_text(22, 748, footer + " Dashed routes contain snapshot-specific connections.", 8, "#8796a8", "400"))
    parts.append("</svg>")
    return "\n".join(parts)


def _comparison_knots(data: dict[str, Any]) -> list[dict[str, Any]]:
    priority = {"high": 0, "medium": 1, "low": 2}
    return sorted((knot for knot in data["knots"] if "comparison" in knot),
                  key=lambda knot: (priority[knot["severity"]], knot["id"]))


def _wiring_delta(data: dict[str, Any]) -> str:
    if data["after"] is None:
        return "After not run; no completed change is inferred."
    before = {(edge["feature"], edge["file"]) for edge in data["before"]["edges"]}
    after = {(edge["feature"], edge["file"]) for edge in data["after"]["edges"]}
    if before == after:
        return f"Feature/file connections unchanged: {len(before)} before, {len(after)} after."
    return f"Feature/file connections: {len(before & after)} retained, {len(after - before)} added, {len(before - after)} removed."


def _wrapped_svg(x: int, y: float, value: str, *, width: int = 62, size: int = 21,
                 color: str = "#dce6f2", code: bool = False) -> tuple[list[str], float]:
    parts = []
    if code:
        value = textwrap.dedent(value)
    for source_line in value.splitlines() or [""]:
        lines = textwrap.wrap(source_line, width, replace_whitespace=False,
                              drop_whitespace=not code, expand_tabs=True) or [""]
        for line in lines:
            extra = 'style="font-family:Consolas,monospace" xml:space="preserve"' if code else ""
            parts.append(_svg_text(x, y, line, size, color, extra=extra))
            y += size + 9
    return parts, y


def _comparison_side_svg(side: dict[str, Any], label: str, x: int, top: float, color: str) -> tuple[list[str], float]:
    parts = [_svg_text(x + 24, top + 37, label, 22, color, "700")]
    body, y = _wrapped_svg(x + 24, top + 76, side["summary"])
    parts.extend(body)
    for snippet in side["snippets"]:
        y += 14
        block_top = y
        source, y = _wrapped_svg(x + 24, y + 26, f'{snippet["path"]}:{snippet["line"]}',
                                 size=18, color="#a9bed5")
        code, code_end = _wrapped_svg(x + 24, y + 6, snippet["code"], width=72, size=16,
                                      color="#edf5ff", code=True)
        parts.append(f'<rect x="{x + 12}" y="{block_top:.1f}" width="720" height="{code_end - block_top + 12:.1f}" rx="7" fill="#0a111d"/>')
        parts.extend(source)
        parts.extend(code)
        y = code_end + 13
    return parts, y + 8


def _path_location(node: dict[str, Any], side: dict[str, Any]) -> str:
    source = side["snippets"][node["snippet"] - 1]
    return f'{source["path"]}:{source["line"]}'


def _path_nodes(path: dict[str, Any]) -> list[dict[str, Any]]:
    return [path["from"], *path.get("via", []), path["to"]]


def render_path_comparison_svg(knot: dict[str, Any], path_id: str) -> str:
    """Draw every supplied handoff, keeping source owners in the same positions."""
    comparison = knot["comparison"]
    paths = {phase: next(path for path in comparison[phase]["paths"] if path["id"] == path_id)
             for phase in ("before", "after")}
    owners: list[str] = []
    nodes = {}
    for phase, path in paths.items():
        nodes[phase] = [(comparison[phase]["snippets"][node["snippet"] - 1]["path"], node)
                        for node in _path_nodes(path)]
        for owner, _ in nodes[phase]:
            if owner not in owners:
                owners.append(owner)
    # The two diagonal handoffs cross when a four-owner detour is present.
    # The direct replacement runs across the top between the same endpoints.
    slots = [(0, 0), (1, 1), (0, 1), (1, 0), (0, 2), (1, 2), (0, 3), (1, 3)]
    if len(owners) == 2:
        slots = [(0, 0), (1, 0)]
    positions = dict(zip(owners, slots, strict=False))
    node_height = 112
    for phase in paths:
        for _, node in nodes[phase]:
            label_lines = len(_wrapped_svg(0, 0, node["label"], width=18, size=22)[0])
            source_lines = len(_wrapped_svg(0, 0, _path_location(node, comparison[phase]), width=23, size=17)[0])
            node_height = max(node_height, 28 + label_lines * 31 + source_lines * 26)
    for owner in owners:
        ghost_lines = len(_wrapped_svg(0, 0, owner, width=21, size=19)[0])
        node_height = max(node_height, 65 + ghost_lines * 28)
    rows = max(row for _, row in positions.values()) + 1
    title_lines, _ = _wrapped_svg(28, 40, paths["before"]["label"], width=65, size=29, color="#f2f6fb")
    header_extra = (len(title_lines) - 1) * 38
    value_lines = max(len(_wrapped_svg(0, 0, path["value"], width=48, size=18)[0]) for path in paths.values())
    graph_top = 190 + (value_lines - 1) * 27
    bottom = graph_top + rows * node_height + (rows - 1) * 116
    height = bottom + 105 + header_extra
    ordinal = next(index for index, path in enumerate(comparison["before"]["paths"]) if path["id"] == path_id)
    prefix = f'route-{knot["id"]}-{ordinal}'
    counts = {phase: len(nodes[phase]) - 1 for phase in paths}
    parts = [
        f'<svg class="path-comparison" xmlns="http://www.w3.org/2000/svg" width="1120" height="{height}" viewBox="0 0 1120 {height}" role="img" aria-labelledby="{prefix}-title {prefix}-description">',
        f'<title id="{prefix}-title">{_escape(paths["before"]["label"])}: {_escape(knot["title"])}</title>',
        f'<desc id="{prefix}-description">Every arrow is a supplied source-to-source handoff. The same owners keep their positions. Owners outside a route remain visible; crossings are layout, not extra connections.</desc>',
        f'<rect width="1120" height="{height}" rx="16" fill="#0a101b"/>',
        *title_lines,
        _svg_text(28, 73 + header_extra, "Follow the arrows. Numbers identify each source-to-source handoff.", 18, "#b9c9db"),
        f'<g transform="translate(0 {header_extra})">',
    ]
    for phase, offset, heading in (("before", 16, "BEFORE"), ("after", 576, "AFTER")):
        side = comparison[phase]
        active = dict(nodes[phase])
        count = counts[phase]
        marker_id = f'{prefix}-{phase}-arrow'
        parts.extend([
            f'<g class="route-phase" data-phase="{phase}" transform="translate({offset} 0)">',
            f'<rect x="0" y="100" width="528" height="{bottom - 78}" rx="12" fill="#101b2b" stroke="#35465d"/>',
            _svg_text(20, 134, f'{heading} / {count} handoff' + ("s" if count != 1 else ""), 23, "#f2f6fb", "700"),
            *_wrapped_svg(20, 164, paths[phase]["value"], width=48, size=18, color="#f4a261")[0],
            f'<defs><marker id="{marker_id}" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M 0 0 L 12 6 L 0 12 Z" fill="#f4a261"/></marker></defs>',
        ])
        for index, ((source, _), (target, _)) in enumerate(zip(nodes[phase], nodes[phase][1:]), 1):
            col_a, row_a = positions[source]
            col_b, row_b = positions[target]
            ax, ay = 20 + col_a * 270, graph_top + row_a * (node_height + 116)
            bx, by = 20 + col_b * 270, graph_top + row_b * (node_height + 116)
            if row_a == row_b:
                sx, sy = ax + (218 if col_b > col_a else 0), ay + node_height / 2
                tx, ty = bx + (0 if col_b > col_a else 218), by + node_height / 2
                route = f'M {sx} {sy} L {tx} {ty}'
            else:
                sx, sy = ax + 109, ay + (node_height if row_b > row_a else 0)
                tx, ty = bx + 109, by + (0 if row_b > row_a else node_height)
                mid = (sy + ty) / 2
                route = f'M {sx} {sy} C {sx} {mid} {tx} {mid} {tx} {ty}'
            parts.append(f'<path d="{route}" fill="none" stroke="#101b2b" stroke-width="12"/>')
            parts.append(f'<path class="route-wire" data-from="{_escape(source)}" data-to="{_escape(target)}" d="{route}" fill="none" stroke="#f4a261" stroke-width="4" marker-end="url(#{marker_id})"/>')
            # Put handoff numbers near the starting owner, away from crossings.
            label_x, label_y = sx + (tx - sx) * .22, sy + (ty - sy) * .22
            parts.append(f'<circle cx="{label_x}" cy="{label_y}" r="13" fill="#f4a261" stroke="#101b2b" stroke-width="3"/>')
            parts.append(_svg_text(label_x, label_y + 5, str(index), 15, "#10131b", "700", 'text-anchor="middle"'))
        for owner in owners:
            col, row = positions[owner]
            x, y = 20 + col * 270, graph_top + row * (node_height + 116)
            is_active = owner in active
            parts.append(f'<g class="route-owner" data-file="{_escape(owner)}" data-active="{str(is_active).lower()}" transform="translate({x} {y})">')
            border = 'stroke="#7186a0"' if is_active else 'stroke="#435267" stroke-dasharray="5 5"'
            parts.append(f'<rect width="218" height="{node_height}" rx="9" fill="#0a101b" {border} stroke-width="2"/>')
            if is_active:
                node = active[owner]
                label, _ = _wrapped_svg(14, 31, node["label"], width=18, size=22)
                location = _path_location(node, side)
                lines = len(_wrapped_svg(0, 0, location, width=23, size=17)[0])
                source, _ = _wrapped_svg(14, node_height - 17 - (lines - 1) * 26, location, width=23, size=17, color="#b9c9db")
                parts.extend([*label, *source])
            else:
                label, _ = _wrapped_svg(14, 31, owner, width=21, size=19, color="#8495aa")
                parts.extend([*label, _svg_text(14, node_height - 19, "outside this route", 17, "#8495aa")])
            parts.append('</g>')
        parts.append('</g>')
    if counts["before"] != counts["after"]:
        takeaway = f'{counts["before"]} handoffs before → {counts["after"]} after. Wire color stays the same in both panels.'
    else:
        takeaway = "Compare what each file does and what it passes across the boundary."
    parts.append(_svg_text(28, bottom + 57, takeaway, 19, "#dce6f2"))
    parts.append(_svg_text(28, bottom + 87, "Positions stay fixed across panels. Only the supplied handoffs are drawn.", 17, "#a9bed5"))
    return "\n".join([*parts, '</g>', '</svg>'])


def render_knot_routes_svg(knot: dict[str, Any], path_ids: tuple[str, ...]) -> str:
    """Present related source routes together without changing their handoffs."""
    title = f'Knot #{knot["id"]} · {knot["title"]}'
    heading, bottom = _wrapped_svg(28, 45, title, width=66, size=30, color="#f2f6fb")
    top = int(bottom) + 12
    parts = list(heading)
    for path_id in path_ids:
        route = render_path_comparison_svg(knot, path_id)
        route_height = int(re.search(r'height="(\d+)"', route).group(1))
        parts.append(route.replace("<svg ", f'<svg y="{top}" ', 1))
        top += route_height + 12
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="{top}" viewBox="0 0 1120 {top}" role="img" aria-labelledby="knot-routes-title knot-routes-description">',
        f'<title id="knot-routes-title">{_escape(title)}</title>',
        f'<desc id="knot-routes-description">{_escape(knot["comparison"]["after"]["summary"])}</desc>',
        f'<rect width="1120" height="{top}" rx="16" fill="#070c14"/>',
        *parts,
        "</svg>",
    ])


def _path_height(path: dict[str, Any], side: dict[str, Any]) -> int:
    content_heights = []
    for endpoint in ("from", "to"):
        node = path[endpoint]
        labels = len(_wrapped_svg(0, 0, node["label"], width=18, size=24)[0])
        locations = len(_wrapped_svg(0, 0, _path_location(node, side), width=28, size=15)[0])
        content_heights.append(46 + labels * 33 + locations * 24)
    values = len(_wrapped_svg(0, 0, path["value"], width=16, size=20)[0])
    return max(126, *content_heights, 56 + values * 58)


def _path_node_svg(node: dict[str, Any], side: dict[str, Any], x: int, y: float, height: int) -> list[str]:
    location = _path_location(node, side)
    text, _ = _wrapped_svg(x + 14, y + 34, node["label"], width=18, size=24)
    lines = len(_wrapped_svg(0, 0, location, width=28, size=15)[0])
    references, _ = _wrapped_svg(x + 14, y + height - 20 - (lines - 1) * 24, location, width=28, size=15, color="#a9bed5")
    return [
        f'<g><title>{_escape(location + " · " + node["label"])}</title>',
        f'<rect x="{x}" y="{y:.1f}" width="248" height="{height}" rx="10" fill="#0a111d" stroke="#647d98" stroke-width="2"/>',
        *text, *references, '</g>',
    ]


def _comparison_paths_svg(side: dict[str, Any], label: str, x: int, top: float, color: str,
                          summary_height: int, heights: list[int]) -> tuple[list[str], float]:
    parts = [_svg_text(x + 24, top + 37, label, 22, color, "700")]
    body, _ = _wrapped_svg(x + 24, top + 76, side["summary"])
    parts.extend(body)
    y = top + 76 + summary_height + 12
    for path, height in zip(side["paths"], heights, strict=True):
        heading, y = _wrapped_svg(x + 24, y + 18, path["label"], width=62, size=18, color="#b9cde0")
        parts.extend(heading)
        y += 5
        parts.extend(_path_node_svg(path["from"], side, x + 24, y, height))
        parts.extend(_path_node_svg(path["to"], side, x + 472, y, height))
        middle = y + height / 2
        parts.append(f'<path d="M {x + 282} {middle:.1f} H {x + 459}" stroke="#7cb9d6" stroke-width="3"/>')
        parts.append(f'<path d="M {x + 451} {middle - 7:.1f} L {x + 464} {middle:.1f} L {x + 451} {middle + 7:.1f}" fill="none" stroke="#7cb9d6" stroke-width="3"/>')
        transfer, _ = _wrapped_svg(x + 292, middle + 30, path["value"], width=16, size=20, color="#a9d5e9")
        parts.extend(transfer)
        y += height + 24
    return parts, y


def _direct_route(knots: list[dict[str, Any]]) -> tuple[int, str] | None:
    """Find the fixed route that removes the most intermediate owners."""
    best = None
    most_removed = 0
    for knot in knots:
        if knot["status"] != "fixed":
            continue
        before, after = (knot["comparison"][phase] for phase in ("before", "after"))
        for previous, current in zip(before.get("paths", []), after.get("paths", []), strict=True):
            removed = len(previous.get("via", []))
            if removed <= most_removed or current.get("via"):
                continue
            old_ends = tuple(before["snippets"][previous[end]["snippet"] - 1]["path"] for end in ("from", "to"))
            new_ends = tuple(after["snippets"][current[end]["snippet"] - 1]["path"] for end in ("from", "to"))
            if old_ends == new_ends:
                best = (knot["id"], previous["id"])
                most_removed = removed
    return best


def _embed_route(knot: dict[str, Any], path_id: str, y: float) -> tuple[str, float]:
    svg = render_path_comparison_svg(knot, path_id)
    height = int(re.search(r'height="(\d+)"', svg).group(1))
    scaled_height = height * 1504 / 1120
    embedded = (svg.replace('<svg ', f'<svg x="48" y="{y}" ', 1)
                .replace('width="1120"', 'width="1504"', 1)
                .replace(f'height="{height}"', f'height="{scaled_height}"', 1))
    return embedded, y + scaled_height + 24


def render_svg(data: dict[str, Any]) -> str:
    """Explain supplied source changes, falling back to the wiring map for legacy evidence."""
    comparisons = _comparison_knots(data)
    if not comparisons:
        svg = render_wiring_svg(data)
        if data["after"] is not None:
            notice = _svg_text(22, 733, "No source change explanations supplied; wiring alone does not explain the refactor.", 9, "#e7be8e")
            svg = svg.replace("</svg>", notice + "\n</svg>")
        return svg
    overview = (render_wiring_svg(data)
                .replace('id="svg-title"', 'id="wiring-title"')
                .replace('id="svg-description"', 'id="wiring-description"')
                .replace('aria-labelledby="svg-title svg-description"', 'aria-labelledby="wiring-title wiring-description"'))
    displayed = comparisons[:3]
    lead = _direct_route(displayed)
    parts = []
    overview_top = 0
    route_description = ""
    if lead:
        knot_id, path_id = lead
        knot = next(record for record in displayed if record["id"] == knot_id)
        for phase in ("before", "after"):
            path = next(record for record in knot["comparison"][phase]["paths"] if record["id"] == path_id)
            owners = " → ".join(node["label"] for node in _path_nodes(path))
            route_description += f"{phase.title()}: {owners}. "
        title, y = _wrapped_svg(48, 52, data["title"], width=80, size=32, color="#f2f6fb")
        parts.extend(title)
        parts.append(_svg_text(48, y + 4, f"DIRECT ROUTE · KNOT #{knot_id}", 19, "#f4a261", "700"))
        route, bottom = _embed_route(knot, path_id, y + 24)
        parts.append(route)
        parts.append(_svg_text(48, bottom + 12, "FULL FEATURE / FILE WIRING", 20, "#dce6f2", "700"))
        overview_top = int(bottom + 34)
        overview = overview.replace('<svg ', f'<svg y="{overview_top}" ', 1)
    parts.extend([overview, _svg_text(48, overview_top + 805, "WHAT WAS UNTIED", 26, "#f2f6fb", "700")])
    parts.append(_svg_text(48, overview_top + 840, _wiring_delta(data), 21, "#bbcbdc"))
    parts.append(_svg_text(48, overview_top + 872, f"Showing {len(displayed)} of {len(comparisons)} source-based knot explanations; all are in untangle.html.", 17, "#95a9c0"))
    parts.append(_svg_text(48, overview_top + 907, "Wire colors identify features. Green numbered badges mean a supplied fixed status, supported by verification records.", 17, "#a9bed5"))
    parts.append(_svg_text(48, overview_top + 934, "Required: an after snapshot, passing build, and passing tests or an explicit no-tests record. The renderer does not run them.", 17, "#a9bed5"))
    y = overview_top + 985
    for knot in displayed:
        comparison = knot["comparison"]
        status_color = "#7be3af" if knot["status"] == "fixed" else "#ff929a"
        parts.append(_svg_text(48, y, f'KNOT #{knot["id"]} / {knot["category"]} / {knot["status"]}', 18, status_color, "700"))
        heading, y = _wrapped_svg(48, y + 38, knot["title"], width=91, size=28, color="#f2f6fb")
        parts.extend(heading)
        if "paths" in comparison["before"]:
            parts.append(_svg_text(48, y + 4, "DATA FLOW / arrows label what crosses each source boundary; these are not module dependency edges.", 17, "#95a9c0"))
            y += 35
        top = y + 8
        after_color = status_color
        route_ids = [path["id"] for index, path in enumerate(comparison["before"].get("paths", []))
                     if path.get("via") or comparison["after"]["paths"][index].get("via")]
        for path_id in route_ids:
            if (knot["id"], path_id) == lead:
                parts.append(_svg_text(48, top + 14, "See the direct route at the top for the source handoffs.", 19, "#a9bed5"))
                top += 34
            else:
                route, top = _embed_route(knot, path_id, top)
                parts.append(route)
        card_sides = {phase: {**comparison[phase], "paths": [path for path in comparison[phase].get("paths", []) if path["id"] not in route_ids]}
                      for phase in ("before", "after")}
        if "paths" in comparison["before"]:
            summary_height = 30 * max(len(_wrapped_svg(0, 0, comparison[phase]["summary"])[0]) for phase in ("before", "after"))
            heights = [max(_path_height(before, card_sides["before"]), _path_height(after, card_sides["after"])) for before, after in zip(card_sides["before"]["paths"], card_sides["after"]["paths"], strict=True)]
            before_parts, before_end = _comparison_paths_svg(card_sides["before"], "BEFORE / observed baseline", 48, top, "#ff929a", summary_height, heights)
            after_parts, after_end = _comparison_paths_svg(card_sides["after"], f'AFTER / {knot["status"]}', 808, top, after_color, summary_height, heights)
        else:
            before_parts, before_end = _comparison_side_svg(comparison["before"], "BEFORE / observed baseline", 48, top, "#ff929a")
            after_parts, after_end = _comparison_side_svg(comparison["after"], f'AFTER / {knot["status"]}', 808, top, after_color)
        bottom = max(before_end, after_end)
        for x, side in ((48, before_parts), (808, after_parts)):
            parts.append(f'<rect x="{x}" y="{top:.1f}" width="744" height="{bottom - top:.1f}" rx="12" fill="#111e2e" stroke="#334960"/>')
            parts.extend(side)
        y = bottom + 36
        for label, value in (("WHY THIS HELPS", comparison["benefit"]), ("WHAT STAYED THE SAME", comparison["preserved"])):
            parts.append(_svg_text(48, y, label, 17, "#77cce6", "700"))
            body, y = _wrapped_svg(48, y + 31, value, width=132, size=21)
            parts.extend(body)
            y += 18
        checks = dict.fromkeys(f'{entry["kind"]}: {entry["result"]}' for entry in knot["verification"])
        check_label = "Recorded checks supporting fixed status: " if knot["status"] == "fixed" else "Recorded checks: "
        body, y = _wrapped_svg(48, y, check_label + ("; ".join(checks) or "none supplied"), width=139, size=18, color="#abc1d6")
        parts.extend(body)
        y += 47
    parts.append(_svg_text(48, y, "Paths and excerpts are supplied evidence. Inspect full source excerpts, revisions and verification records in untangle.html.", 17, "#95a9c0"))
    height = int(y + 35)
    return "\n".join([
        f'<svg class="comparison change-comparison" xmlns="http://www.w3.org/2000/svg" width="1600" height="{height}" viewBox="0 0 1600 {height}" role="img" aria-labelledby="svg-title svg-description">',
        f'<title id="svg-title">{_escape(data["title"])} · source changes before and after</title>',
        f'<desc id="svg-description">{_escape(route_description)}Source-referenced paths or matched excerpts, the reason for each change, preserved behavior and recorded checks. Full source excerpts remain in the HTML.</desc>',
        f'<rect width="1600" height="{height}" rx="18" fill="#070c14"/>',
        *parts, '</svg>',
    ])


def _paths_html(side: dict[str, Any]) -> str:
    paths = []
    for path in side.get("paths", []):
        nodes = []
        for node in _path_nodes(path):
            source = side["snippets"][node["snippet"] - 1]
            nodes.append(f'<div class="flow-node"><strong>{_escape(node["label"])}</strong><code>{_escape(source["path"])}:{source["line"]}</code></div>')
        transfer = f'<div class="flow-transfer"><span aria-hidden="true">→</span><small>{_escape(path["value"])}</small></div>'
        chain_class = " chained" if path.get("via") else ""
        paths.append(f'<div class="flow-path"><h5>{_escape(path["label"])}</h5><div class="flow-route{chain_class}">{transfer.join(nodes)}</div></div>')
    return "".join(paths)


def _comparison_html(data: dict[str, Any]) -> str:
    comparisons = _comparison_knots(data)
    if not comparisons:
        message = ("After not run. The map shows the baseline; no completed change is inferred." if data["after"] is None
                   else "No source change explanations supplied. Wiring alone does not explain what moved or why.")
        return f'<section class="change-intro"><h2>What changed</h2><p>{_escape(message)}</p></section>'
    chunks = [f'<section class="change-intro"><h2>What changed</h2><p>{_escape(_wiring_delta(data))}</p>'
              '<p>Wire colors identify features and stay stable. Green numbered badges show a supplied fixed status: an after snapshot, passing build, and passing tests or an explicit no-tests record. The renderer validates those records; it does not execute the checks.</p></section>']
    for knot in comparisons:
        comparison = knot["comparison"]
        route_diagrams = "".join(render_path_comparison_svg(knot, path["id"])
                                 for index, path in enumerate(comparison["before"].get("paths", []))
                                 if path.get("via") or comparison["after"]["paths"][index].get("via"))
        sides = []
        for phase in ("before", "after"):
            side = comparison[phase]
            snippets = "".join(
                f'<div class="source-excerpt"><p class="source-location">{_escape(snippet["path"])}:{snippet["line"]}</p>'
                f'<pre><code>{_escape(snippet["code"])}</code></pre></div>' for snippet in side["snippets"]
            )
            label = "Before / observed baseline" if phase == "before" else f'After / {knot["status"]}'
            resolved = " fixed" if phase == "after" and knot["status"] == "fixed" else ""
            if "paths" in side:
                snippets = f'<details class="change-source-details"><summary>View exact source excerpts ({len(side["snippets"])})</summary>{snippets}</details>'
            sides.append(f'<section class="change-side {phase}{resolved}"><h4>{_escape(label)}</h4><p>{_escape(side["summary"])}</p>{_paths_html(side)}{snippets}</section>')
        checks = "; ".join(dict.fromkeys(f'{entry["kind"]}: {entry["result"]}' for entry in knot["verification"])) or "none supplied"
        check_label = "Recorded checks supporting fixed status" if knot["status"] == "fixed" else "Recorded checks"
        chunks.append(
            f'<article class="change-record" data-knot-id="{knot["id"]}"><h3>#{knot["id"]} {_escape(knot["title"])}</h3>'
            f'<p class="muted">{_escape(knot["category"])} · {_escape(knot["status"])}</p>{route_diagrams}<div class="change-sides">{"".join(sides)}</div>'
            f'<div class="change-reason"><h4>Why this helps</h4><p>{_escape(comparison["benefit"])}</p>'
            f'<h4>What stayed the same</h4><p>{_escape(comparison["preserved"])}</p><p class="muted">{check_label}: {_escape(checks)}</p></div></article>'
        )
    missing = len(data["knots"]) - len(comparisons)
    if missing:
        chunks.append(f'<p class="muted">{missing} knot(s) have no source change explanation; inspect their full evidence in the knot register.</p>')
    return "".join(chunks)


def _feature_filter_html(features: list[dict[str, str]]) -> str:
    chunks = []
    for index, feature in enumerate(features):
        color = FEATURE_COLORS[index]
        chunks.append(
            f'<button type="button" class="feature-filter" data-feature-index="{index}" aria-pressed="true">'
            f'<span class="feature-dot" style="--feature-color:{color}" aria-hidden="true"></span>{_escape(feature["label"])}'
            "</button>"
        )
    return "".join(chunks)


def _knot_html(knot: dict[str, Any], feature_labels: dict[str, str]) -> str:
    state_class = "resolved" if knot["status"] == "fixed" else "unresolved"
    feature_html = ", ".join(_escape(feature_labels[feature_id]) for feature_id in knot["features"])
    locations = "".join(
        f'<li><code>{_escape(location["path"])}</code><span> line {location["line"]}</span></li>'
        for location in knot["locations"]
    )
    verifications = "".join(
        "<li>"
        f'<span class="verify-kind">{_escape(entry["kind"])}</span> · <code>{_escape(entry["command"])}</code> · '
        f'<span class="verify-result result-{_escape(entry["result"])}">{_escape(entry["result"])}</span>'
        + (f'<p>{_escape(entry["note"])}</p>' if "note" in entry else "")
        + "</li>"
        for entry in knot["verification"]
    ) or '<li class="muted">No verification entries supplied.</li>'
    return (
        f'<details class="knot-record" data-knot-id="{knot["id"]}">'
        f'<summary><span class="knot-badge {state_class}">#{knot["id"]}</span>'
        f'<span class="knot-title">{_escape(knot["title"])}</span>'
        f'<span class="knot-meta">{_escape(knot["severity"])} · {_escape(knot["status"])}</span></summary>'
        '<div class="knot-body">'
        f'<p><b>Category:</b> {_escape(knot["category"])} · <b>Features:</b> {feature_html}</p>'
        f'<p><b>Evidence:</b> {_escape(knot["evidence"])}</p>'
        f'<p><b>Remedy:</b> {_escape(knot["remedy"])}</p>'
        f'<h4>Baseline locations</h4><ul>{locations}</ul>'
        f'<h4>Verification records</h4><ul>{verifications}</ul>'
        '</div></details>'
    )


def _edge_html(snapshot_name: str, snapshot: dict[str, Any], features: dict[str, dict[str, str]], feature_lookup: dict[str, int]) -> str:
    chunks = []
    for edge in snapshot["edges"]:
        feature = features[edge["feature"]]
        feature_index = feature_lookup[edge["feature"]]
        evidence = "".join(
            '<li><code>' + _escape(item["path"]) + f':{item["line"]}</code> '
            + f'<span class="evidence-kind">{_escape(item["kind"])}</span>'
            + f'<p>{_escape(item["note"])}</p></li>'
            for item in edge["evidence"]
        )
        chunks.append(
            f'<li class="edge-record" data-feature-index="{feature_index}">'
            '<details><summary>'
            f'<span class="snapshot-label">{_escape(snapshot_name)}</span>'
            f'<span class="feature-chip" style="--feature-color:{FEATURE_COLORS[feature_index]}">{_escape(feature["label"])}</span>'
            '<span class="edge-arrow" aria-label="to">→</span>'
            f'<code>{_escape(edge["file"])}</code>'
            f'<span class="evidence-count">{len(edge["evidence"])} evidence</span>'
            f'</summary><ol>{evidence}</ol></details></li>'
        )
    return "".join(chunks)


def _file_inventory_html(data: dict[str, Any]) -> str:
    groups, _ = _union_groups(data["before"], data["after"])
    group_for_file = {path: group["label"] for group in groups for path in group["members"]}
    chunks = []
    for snapshot_name in ("before", "after"):
        snapshot = data[snapshot_name]
        if snapshot is None:
            continue
        pair_counts: dict[str, int] = defaultdict(int)
        for edge in snapshot["edges"]:
            pair_counts[edge["file"]] += 1
        for path in snapshot["files"]:
            count = pair_counts[path]
            reachability = f"{count} supplied proven feature/file pair(s)" if count else "No supplied proven feature/file pair"
            chunks.append(
                f'<li class="file-record" data-snapshot="{snapshot_name}" data-file-path="{_escape(path)}">'
                f'<span class="snapshot-label">{snapshot_name.upper()}</span> <code>{_escape(path)}</code>'
                f'<p>Overview group: {_escape(group_for_file[path])} · {reachability}</p></li>'
            )
    return "".join(chunks)


def render_html(data: dict[str, Any], svg: str) -> str:
    feature_lookup = _feature_indices(data["features"])
    feature_by_id = {feature["id"]: feature for feature in data["features"]}
    feature_labels = {feature["id"]: feature["label"] for feature in data["features"]}
    before_evidence = sum(len(edge["evidence"]) for edge in data["before"]["edges"])
    before_meta = f'<li><b>Before revision:</b> {_escape(data["before"]["revision"])}<br><b>Coverage:</b> {_escape(data["before"]["coverage"])}</li>'
    if data["after"] is None:
        after_meta = '<li><b>After:</b> not run; after is null in the evidence manifest.</li>'
        after_edges = '<li class="inventory-empty">No after snapshot was supplied, so no after edges are inferred.</li>'
    else:
        after_meta = f'<li><b>After revision:</b> {_escape(data["after"]["revision"])}<br><b>Coverage:</b> {_escape(data["after"]["coverage"])}</li>'
        after_edges = _edge_html("AFTER", data["after"], feature_by_id, feature_lookup)

    knot_records = "".join(_knot_html(knot, feature_labels) for knot in data["knots"])
    before_edges = _edge_html("BEFORE", data["before"], feature_by_id, feature_lookup)
    edge_count = len(data["before"]["edges"]) + (len(data["after"]["edges"]) if data["after"] else 0)
    evidence_count = before_evidence + (sum(len(edge["evidence"]) for edge in data["after"]["edges"]) if data["after"] else 0)
    knots_by_status = {status: sum(knot["status"] == status for knot in data["knots"]) for status in sorted(STATUSES)}
    status_summary = " · ".join(f"{status} {count}" for status, count in knots_by_status.items())
    grouping_note = "Folder groups use the union of before/after paths; counts and edges are panel-specific." if _union_groups(data["before"], data["after"])[1] else "Files are shown individually in the overview."
    file_inventory = _file_inventory_html(data)
    change_explanations = _comparison_html(data)
    if _comparison_knots(data):
        svg = render_wiring_svg(data)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(data["title"])} · Untangle wiring map</title>
<style>
:root{{--bg:#070c14;--panel:#0c1420;--panel2:#111d2b;--line:#26354a;--text:#edf3fb;--muted:#9aabc0;--accent:#72d3ef;--red:#e24d5b;--green:#50c78b}}
*{{box-sizing:border-box}}
body{{margin:0;background:radial-gradient(ellipse at 20% -10%,#142238 0,transparent 40%),var(--bg);color:var(--text);font:15px/1.5 Arial,Helvetica,sans-serif}}
main{{max-width:1640px;margin:0 auto;padding:22px clamp(16px,2vw,32px) 50px}}
a{{color:#83dafa}}
header{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 24px;align-items:end;margin:0 2px 8px}}
.eyebrow{{color:#77cce6;font-size:11px;font-weight:700;letter-spacing:.14em;text-transform:uppercase}}
h1{{font-size:clamp(25px,3vw,39px);line-height:1.1;margin:3px 0 0;overflow-wrap:anywhere}}
.scope{{color:#bbc8d8;max-width:1000px;margin:6px 0 0}}
.totals{{text-align:right;color:#c0cddd;font-size:12px;white-space:nowrap}}
.totals strong{{display:block;font-size:22px;color:#fff}}
.toolbar{{display:flex;align-items:flex-start;gap:14px;flex-wrap:wrap;margin:14px 0 9px}}
.search-box{{flex:1 1 340px;min-width:230px}}
label{{display:block;color:#aebdd0;font-size:12px;font-weight:700;margin-bottom:5px}}
input[type=search]{{width:100%;border:1px solid #34445b;border-radius:8px;background:#0b1320;color:#f3f7fc;padding:10px 12px;font:inherit;outline:none}}
input[type=search]:focus,button:focus-visible,summary:focus-visible{{outline:2px solid #6fd5f1;outline-offset:2px}}
details.control,details.panel{{border:1px solid var(--line);border-radius:9px;background:#0b1320}}
details.control{{flex:0 1 auto;min-width:215px;max-width:100%;padding:9px 12px}}
summary{{cursor:pointer}}
details.control>summary{{font-size:13px;font-weight:700;color:#e1e9f3}}
.feature-filters{{display:flex;flex-wrap:wrap;gap:7px;margin-top:11px;max-width:700px}}
.feature-filter{{display:inline-flex;gap:7px;align-items:center;border:1px solid #34445b;border-radius:999px;background:#101b29;color:#d9e4ef;padding:6px 9px;font:inherit;font-size:12px;cursor:pointer}}
.feature-filter[aria-pressed=false]{{opacity:.45;text-decoration:line-through}}
.feature-dot{{width:9px;height:9px;border-radius:50%;background:var(--feature-color);flex:none}}
.filter-help,.result-count{{font-size:11px;color:#94a5ba;margin:9px 0 0}}
figure{{margin:0;border:1px solid #233249;border-radius:13px;background:#090f19;padding:8px;overflow:hidden}}
figcaption{{padding:4px 8px 9px;color:#9fadc0;font-size:12px}}
.diagram-scroll{{overflow:auto;overscroll-behavior-inline:contain}}
.comparison{{display:block;width:100%;height:auto;max-height:calc(100vh - 290px);min-width:0;object-fit:contain}}
.edge{{transition:opacity .15s}}
.is-dim{{opacity:.16}}
.svg-knot-badge.selected-knot rect{{stroke:#fff;stroke-width:1.8}}
.details-panel{{margin-top:12px}}
details.panel>summary{{padding:12px 15px;font-weight:700;color:#e7eef7}}
.panel-body{{border-top:1px solid var(--line);padding:15px;display:grid;grid-template-columns:minmax(280px,.85fr) minmax(0,1.4fr);gap:18px}}
.source-coverage{{grid-column:1/-1;min-width:0;overflow-wrap:anywhere}}
.details-grid{{grid-column:1/-1;display:grid;grid-template-columns:minmax(280px,.85fr) minmax(0,1.4fr);gap:18px}}
.details-grid,.details-grid>section{{min-width:0;overflow-wrap:anywhere}}
h2{{font-size:17px;margin:0 0 7px}}
h3{{font-size:14px;margin:18px 0 8px}}
h4{{font-size:12px;margin:13px 0 3px;color:#afc0d5}}
.muted,.disclaimer{{color:#9baabe}}
.knot-list,.edge-list{{list-style:none;padding:0;margin:0;display:grid;gap:7px}}
.knot-record,.edge-record{{border:1px solid #25354a;border-radius:8px;background:#0b1320;overflow:hidden}}
.knot-record>summary,.edge-record summary{{display:flex;align-items:center;gap:9px;padding:9px 10px;list-style:none}}
summary::-webkit-details-marker{{display:none}}
.knot-record>summary::after{{content:'+';margin-left:auto;color:#8fa2b7;font-weight:700}}
.knot-record[open]>summary::after{{content:'-'}}
.knot-badge{{display:inline-flex;min-width:37px;height:25px;align-items:center;justify-content:center;border-radius:6px;background:#c93e4b;color:#fff;font-size:11px;font-weight:800;flex:none}}
.knot-badge.resolved{{background:#278355;border:1px solid #50c78b;color:#fff}}
.knot-title{{font-weight:700;overflow-wrap:anywhere}}
.knot-meta{{margin-left:auto;color:#a4b3c5;font-size:11px;white-space:nowrap}}
.knot-body{{padding:0 12px 12px;color:#d0d9e4;font-size:13px;overflow-wrap:anywhere}}
.knot-body p{{margin:8px 0}}
.knot-body ul,.edge-record ol{{padding-left:22px;margin:5px 0}}
.knot-body li,.edge-record li{{margin:6px 0}}
code{{font:12px/1.45 Consolas,'Courier New',monospace;color:#d6e6f5;overflow-wrap:anywhere}}
.snapshot-label{{color:#8496ad;font-size:10px;font-weight:800;letter-spacing:.08em;min-width:45px}}
.feature-chip{{display:inline-flex;align-items:center;gap:6px;color:#ecf4fb;font-size:12px;font-weight:600;max-width:190px;overflow-wrap:anywhere}}
.feature-chip::before{{content:'';width:8px;height:8px;border-radius:50%;background:var(--feature-color);flex:none}}
.edge-arrow{{color:#8ca0b7}}
.evidence-count{{margin-left:auto;color:#8fa1b6;font-size:10px;white-space:nowrap}}
.edge-record>details>ol{{border-top:1px solid #1e2b3d;padding:7px 12px 5px 34px;margin:0;color:#cfdae7;font-size:12px}}
.edge-record p{{margin:4px 0 10px;color:#acbacc;white-space:pre-wrap}}
.evidence-kind,.verify-kind{{color:#75cde8;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}}
.verify-result{{font-weight:700}}
.result-pass{{color:#71d29d}}.result-fail{{color:#ff8188}}.result-blocked{{color:#f4c56f}}.result-not-applicable{{color:#a9b7c9}}
.edge-record[hidden],.knot-record[hidden],.file-record[hidden],.change-record[hidden]{{display:none}}
.file-list{{list-style:none;padding:0;display:grid;gap:7px;max-height:340px;overflow:auto}}
.file-record{{border:1px solid var(--line);border-radius:8px;padding:9px 10px;overflow-wrap:anywhere}}
.file-record p{{margin:4px 0 0;color:var(--muted);font-size:12px}}
.inventory-empty{{border:1px dashed #35455a;border-radius:8px;padding:12px;color:#9baabe}}
.disclaimer{{font-size:11px;max-width:1250px;margin:16px 2px 0}}
.change-intro{{margin:25px 0 12px}}
.change-intro h2{{font-size:24px}}
.change-intro p{{color:#a9bfd4;margin:4px 0}}
.change-record{{margin:0 0 24px;padding:22px;border:1px solid #334960;border-radius:12px;background:#0c1420}}
.change-record h3{{font-size:22px;line-height:1.3;margin:0 0 6px;overflow-wrap:anywhere}}
.change-record>p{{margin:0 0 18px}}
.change-sides{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}}
.path-comparison{{display:block;width:100%;height:auto;margin:18px 0}}
.change-side{{min-width:0;padding:18px;border:1px solid #2f4258;border-radius:9px;background:#111e2e}}
.change-side h4{{font-size:16px;margin:0 0 9px;color:#e8c29a}}
.change-side.before h4{{color:#ff929a}}.change-side.after.fixed h4{{color:#7be3af}}
.change-side>p{{margin:0 0 18px;overflow-wrap:anywhere}}
.source-excerpt{{margin-top:12px;padding:12px;background:#090f19;border-radius:6px}}
.source-location{{margin:0 0 8px;color:#a9bed5;font-size:12px;overflow-wrap:anywhere}}
.source-excerpt pre{{margin:0;overflow-x:auto}}
.source-excerpt pre code{{font:14px/1.65 Consolas,'Courier New',monospace;white-space:pre}}
.change-reason h4{{font-size:14px;color:#77cce6;margin:18px 0 4px}}
.change-reason p{{margin:0;overflow-wrap:anywhere}}
.flow-path{{margin:20px 0}}
.flow-path h5{{font-size:13px;color:#b9cde0;margin:0 0 9px}}
.flow-route{{display:grid;grid-template-columns:minmax(0,1fr) 90px minmax(0,1fr);align-items:stretch}}
.flow-route.chained{{grid-template-columns:minmax(0,1fr)}}
.flow-route.chained .flow-transfer span{{transform:rotate(90deg)}}
.flow-node{{min-width:0;padding:13px 10px;border:1px solid #647d98;border-radius:8px;background:#090f19;display:flex;flex-direction:column;justify-content:space-between;gap:14px}}
.flow-node strong{{font-size:16px;overflow-wrap:anywhere}}.flow-node code{{font-size:11px}}
.flow-transfer{{display:flex;flex-direction:column;justify-content:center;align-items:center;padding:0 5px;color:#a9d5e9;text-align:center}}
.flow-transfer span{{font-size:30px}}.flow-transfer small{{font-size:12px;overflow-wrap:anywhere;max-width:100%}}
.change-source-details{{margin-top:20px;border-top:1px solid #334960;padding-top:12px}}
.change-source-details>summary{{color:#a9d5e9;font-size:13px;font-weight:700}}
@media(max-width:760px){{.change-sides{{grid-template-columns:1fr}}.change-record{{padding:13px}}.change-side{{padding:13px}}.flow-route{{grid-template-columns:1fr}}.flow-transfer{{padding:6px}}.flow-transfer span{{transform:rotate(90deg)}}}}
@media(max-width:760px){{main{{padding:14px 10px 30px}}header{{grid-template-columns:1fr}}.totals{{text-align:left;display:flex;gap:15px;align-items:baseline}}.panel-body,.details-grid{{grid-template-columns:minmax(0,1fr)}}.comparison{{min-width:800px;max-height:none}}.edge-record summary{{flex-wrap:wrap}}.evidence-count{{margin-left:0}}}}
</style>
</head>
<body>
<main>
<header>
<div><div class="eyebrow">Untangle · evidence map</div><h1>{_escape(data["title"])}</h1><p class="scope">{_escape(_truncate(data["scope"], 260))}</p></div>
<div class="totals"><strong>{len(data["knots"])}</strong> knots · {status_summary}</div>
</header>
<section class="toolbar" aria-label="Map controls">
<div class="search-box"><label for="map-search">Search knots, exact edges and source evidence</label><input type="search" id="map-search" placeholder="Feature, path, line, evidence note, knot…" autocomplete="off"><div id="result-count" class="result-count" aria-live="polite">{edge_count} edge records · {evidence_count} evidence records; totals stay unfiltered.</div></div>
<details class="control"><summary>Filter features</summary><div class="feature-filters">{_feature_filter_html(data["features"])}</div><p class="filter-help">Selection dims wiring and filters exact edge records. It does not change the reported totals.</p></details>
</section>
<h2>Before and after wiring</h2>
<figure aria-labelledby="diagram-caption"><figcaption id="diagram-caption">Before on the left · after on the right. Colored wires show supplied feature/file pairs. Dashed routes contain feature/file connections present in that snapshot only; grouped routes may also contain retained connections. Numbered badges connect affected files to the knot explanations below; red marks unresolved knots and green marks fixed knots in the after view. Baseline badges remain red to show the earlier unresolved state. Green is supplied fixed status: an after snapshot, passing build, and passing tests or an explicit no-tests record. The renderer does not run the checks. { _escape(grouping_note) }</figcaption><div class="diagram-scroll">{svg}</div></figure>
{change_explanations}
<details class="panel details-panel" id="details-panel"><summary>Full knot details, source evidence and exact edge inventory</summary>
<div class="panel-body"><section class="source-coverage"><h2>Source snapshots and coverage</h2><ul>{before_meta}{after_meta}</ul></section>
<section class="source-coverage"><details id="file-inventory"><summary>Complete file inventory, including files without proven feature connections</summary>
<p class="muted">Every declared file is listed by snapshot. Search filters this inventory; feature selection filters proven edges only.</p>
<ul class="file-list">{file_inventory or '<li class="inventory-empty">No files supplied.</li>'}</ul></details></section>
<div class="details-grid">
<section><h2>Knot register</h2><p class="muted">{len(data["knots"])} supplied knots · {status_summary}. Expanding a numbered row selects that knot's full evidence.</p>
<div class="knot-list">{knot_records or '<p class="inventory-empty">No knots supplied.</p>'}</div></section>
<section><h2>Exact observed feature/file pairs</h2><p class="muted">{edge_count} pair records · {evidence_count} attached source evidence records across supplied snapshots. Grouping and filtering never remove records from this inventory.</p>
<h3>Before · {_escape(data["before"]["revision"])}</h3><ul class="edge-list">{before_edges or '<li class="inventory-empty">No before edges supplied.</li>'}</ul>
<h3>After · {_escape(data["after"]["revision"]) if data["after"] else 'not run'}</h3><ul class="edge-list">{after_edges or '<li class="inventory-empty">No after edges supplied.</li>'}</ul>
</section></div></div></details>
<p class="disclaimer">{_escape(grouping_note)} Coverage and revisions are supplied by the evidence author. This renderer checks schema shape and references; it does not discover features, prove reachability, verify source truth, or certify completeness. Paths are displayed as text, not executable links. { _escape(data["before"]["coverage"]) }</p>
</main>
<script>
(() => {{
  const search = document.getElementById('map-search');
  const detailsPanel = document.getElementById('details-panel');
  const resultCount = document.getElementById('result-count');
  const featureButtons = Array.from(document.querySelectorAll('.feature-filter'));
  const activeFeatures = new Set(featureButtons.map(button => button.dataset.featureIndex));
  const edgeRows = Array.from(document.querySelectorAll('.edge-record'));
  const knotRows = Array.from(document.querySelectorAll('.knot-record'));
  const changeRows = Array.from(document.querySelectorAll('.change-record'));
  const changeSources = Array.from(document.querySelectorAll('.change-source-details'));
  const changeById = new Map(changeRows.map(row => [row.dataset.knotId, row]));
  const fileRows = Array.from(document.querySelectorAll('.file-record'));
  const fileInventory = document.getElementById('file-inventory');
  const wires = Array.from(document.querySelectorAll('svg .edge[data-feature-index]'));
  const featureNodes = Array.from(document.querySelectorAll('svg .diagram-feature[data-feature-index]'));
  const fileNodes = Array.from(document.querySelectorAll('svg .diagram-file[data-file-group-index]'));
  const knotBadges = Array.from(document.querySelectorAll('svg .svg-knot-badge[data-knot-ids]'));

  function applyFilters() {{
    const query = search.value.trim().toLowerCase();
    if (query) detailsPanel.open = true;
    let shownEdges = 0;
    let shownKnots = 0;
    let shownFiles = 0;
    for (const row of changeRows) {{
      row.hidden = Boolean(query) && !row.textContent.toLowerCase().includes(query);
    }}
    if (query) for (const source of changeSources) {{
      if (source.textContent.toLowerCase().includes(query)) source.open = true;
    }}
    if (query) fileInventory.open = true;
    for (const row of fileRows) {{
      row.hidden = Boolean(query) && !row.textContent.toLowerCase().includes(query);
      if (!row.hidden) shownFiles += 1;
    }}
    for (const row of edgeRows) {{
      const visible = activeFeatures.has(row.dataset.featureIndex) && (!query || row.textContent.toLowerCase().includes(query));
      row.hidden = !visible;
      if (visible) shownEdges += 1;
    }}
    for (const row of knotRows) {{
      const change = changeById.get(row.dataset.knotId);
      const visible = !query || row.textContent.toLowerCase().includes(query) || (change && !change.hidden);
      row.hidden = !visible;
      if (visible) shownKnots += 1;
    }}
    const selectedKnot = knotRows.find(row => row.open);
    const selectedKnotId = selectedKnot ? selectedKnot.dataset.knotId : '';
    for (const badge of knotBadges) {{
      badge.classList.toggle('selected-knot', Boolean(selectedKnotId) && badge.dataset.knotIds.split(' ').includes(selectedKnotId));
    }}
    const connectedGroups = new Set();
    for (const wire of wires) {{
      const visible = activeFeatures.has(wire.dataset.featureIndex);
      wire.style.display = visible ? '' : 'none';
      if (visible) connectedGroups.add(wire.dataset.fileGroupIndex);
    }}
    for (const node of featureNodes) {{
      node.style.display = activeFeatures.has(node.dataset.featureIndex) ? '' : 'none';
    }}
    for (const node of fileNodes) {{
      node.classList.toggle('is-dim', !connectedGroups.has(node.dataset.fileGroupIndex));
    }}
    resultCount.textContent = `${{shownEdges}} of ${{edgeRows.length}} edge records, ${{shownFiles}} of ${{fileRows.length}} file records and ${{shownKnots}} of ${{knotRows.length}} knots shown. Reported totals remain unfiltered.`;
  }}

  for (const button of featureButtons) {{
    button.addEventListener('click', () => {{
      const index = button.dataset.featureIndex;
      if (activeFeatures.has(index)) activeFeatures.delete(index); else activeFeatures.add(index);
      button.setAttribute('aria-pressed', activeFeatures.has(index) ? 'true' : 'false');
      applyFilters();
    }});
  }}
  search.addEventListener('input', applyFilters);
  for (const row of knotRows) {{
    row.addEventListener('toggle', () => {{
      if (row.open) for (const other of knotRows) if (other !== row) other.open = false;
      applyFilters();
    }});
  }}
  applyFilters();
}})();
</script>
</body>
</html>
'''


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            raw_bytes = stream.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise FilesystemError(
            f"cannot read input file '{path}': {exc}",
            context=f"input file '{path}'",
            hint=f"Check that the file exists and is readable from {Path.cwd()}.",
        ) from exc
    if len(raw_bytes) > MAX_INPUT_BYTES:
        raise InputError(
            f"input file '{path}' exceeds the {MAX_INPUT_BYTES}-byte size limit",
            context=f"input file '{path}'",
            hint="Keep the complete evidence scope and use a renderer-supported view size.",
        )
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError(
            f"input file '{path}' is not valid UTF-8",
            context=f"input file '{path}'",
            hint="Save the evidence manifest as UTF-8, then retry the same command.",
        ) from exc
    try:
        raw = json.loads(text, object_pairs_hook=_duplicate_keys)
    except InputError as exc:
        raise InputError(
            str(exc),
            context=f"input file '{path}'",
            hint="Correct the JSON object named in this message, then retry the same command.",
        ) from exc
    except json.JSONDecodeError as exc:
        raise InputError(
            f"invalid JSON in input file '{path}' at line {exc.lineno}, column {exc.colno}: {exc.msg}",
            context=f"input file '{path}'",
            hint=f"Correct the JSON syntax at line {exc.lineno}, column {exc.colno}, then retry.",
        ) from exc
    except RecursionError as exc:
        raise InputError(
            f"JSON in input file '{path}' is nested too deeply",
            context=f"input file '{path}'",
            hint="Reduce unnecessary nesting, then retry the same command.",
        ) from exc
    try:
        return validate_manifest(raw)
    except InputError as exc:
        raise InputError(
            str(exc),
            context=f"input file '{path}'",
            hint="Correct the named schema field, then retry the same command.",
        ) from exc


def _output_dir_path(raw_dir: str) -> Path:
    requested = Path(raw_dir).expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    output_dir = Path(os.path.abspath(requested))
    if output_dir == Path(output_dir.anchor):
        raise SafetyError(
            "output directory cannot be a filesystem root",
            context=f"output directory '{output_dir}'",
            hint="Choose a dedicated output directory below the filesystem root.",
        )
    ancestors = [output_dir, *output_dir.parents]
    for path in ancestors:
        if os.path.lexists(path):
            if path.is_symlink():
                raise SafetyError(
                    f"unsafe output directory contains a symbolic link: {path}",
                    context=f"output directory '{output_dir}'",
                    hint="Choose a directory path whose existing components are not symbolic links.",
                )
            attributes = getattr(path.lstat(), "st_file_attributes", 0)
            if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                raise SafetyError(
                    f"unsafe output directory contains a Windows reparse point: {path}",
                    context=f"output directory '{output_dir}'",
                    hint="Choose a regular directory path with no junctions or other reparse points.",
                )
            if path != output_dir and not path.is_dir():
                raise SafetyError(
                    f"unsafe output directory parent is not a directory: {path}",
                    context=f"output directory '{output_dir}'",
                    hint="Choose an output path below an existing directory.",
                )
    return output_dir


def _prepare_output_dir(raw_dir: str) -> Path:
    output_dir = _output_dir_path(raw_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise FilesystemError(
            f"cannot create output directory '{output_dir}': {exc}",
            context=f"output directory '{output_dir}'",
            hint="Choose an accessible directory and check its parent permissions.",
        ) from exc
    _output_dir_path(str(output_dir))
    if not output_dir.is_dir():
        raise SafetyError(
            "output-dir must resolve to a regular directory",
            context=f"output directory '{output_dir}'",
            hint="Choose an output path that is a regular directory.",
        )
    return output_dir.resolve()


def _inspect_output_dir(raw_dir: str) -> Path:
    output_dir = _output_dir_path(raw_dir)
    if os.path.lexists(output_dir) and not output_dir.is_dir():
        raise SafetyError(
            f"output-dir is not a directory: {output_dir}",
            context=f"output directory '{output_dir}'",
            hint="Choose an output directory path; the renderer will place its three files inside it.",
        )
    return output_dir.resolve(strict=False)


def _check_output_targets(output_dir: Path, input_path: Path, overwrite: bool) -> dict[str, Path]:
    targets = {name: output_dir / name for name in OUTPUT_NAMES}
    input_resolved = input_path.resolve()
    existing: list[str] = []
    for name, target in targets.items():
        if target.resolve(strict=False) == input_resolved:
            raise SafetyError(
                f"unsafe output: {name} would replace the input file",
                context=f"output target '{target}'",
                hint="Choose a different --output-dir so the input file remains untouched.",
            )
        if not os.path.lexists(target):
            continue
        if target.is_symlink() or not target.is_file():
            raise SafetyError(
                f"unsafe output target is not a regular file: {target}",
                context=f"output target '{target}'",
                hint="Choose a fresh --output-dir with no symbolic links or non-file targets.",
            )
        existing.append(name)
    if existing and not overwrite:
        raise SafetyError(
            f"output already exists in '{output_dir}': {', '.join(existing)}",
            context=f"output directory '{output_dir}'",
            hint=(
                "Choose a fresh --output-dir to preserve these files. If replacement is intended, "
                "verify the existing targets before explicitly adding --overwrite."
            ),
        )
    return targets


def _stage_file(output_dir: Path, content: str) -> Path:
    fd, temp_name = tempfile.mkstemp(prefix=".untangle-stage-", suffix=".tmp", dir=output_dir)
    path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise
    return path


def _safe_remove(path: Path, expected: os.stat_result) -> bool:
    try:
        current = path.lstat()
        if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
            expected.st_dev, expected.st_ino, expected.st_size, expected.st_mtime_ns
        ):
            return False
        path.unlink()
        return True
    except OSError:
        return False


def _copy_exclusive(source: Path, target: Path) -> os.stat_result:
    """Copy into a new name without replacing anything, including during recovery."""
    identity = None
    source_mode = None
    try:
        with target.open("xb") as destination:
            identity = os.fstat(destination.fileno())
            try:
                with source.open("rb") as origin:
                    source_mode = stat.S_IMODE(os.fstat(origin.fileno()).st_mode)
                    if hasattr(os, "fchmod"):
                        os.fchmod(destination.fileno(), source_mode)
                    shutil.copyfileobj(origin, destination)
                destination.flush()
                os.fsync(destination.fileno())
            finally:
                identity = os.fstat(destination.fileno())
        if not hasattr(os, "fchmod"):
            os.chmod(target, source_mode)
        return identity
    except BaseException:
        if identity is not None:
            # The exclusive reservation belongs to this copy, even after a short write.
            with contextlib.suppress(OSError):
                current = target.lstat()
                if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                    target.unlink()
        raise


def _publish_no_clobber(source: Path, target: Path) -> os.stat_result:
    try:
        os.link(source, target)
    except OSError as exc:
        if exc.errno not in {errno.EPERM, errno.EACCES, errno.ENOSYS, errno.EOPNOTSUPP, errno.EXDEV, errno.EINVAL}:
            raise
        return _copy_exclusive(source, target)
    return target.lstat()


def _restore_backup(backup: Path, target: Path) -> None:
    if os.name == "nt":
        # Windows rename refuses an existing destination and preserves the file metadata.
        os.rename(backup, target)
        return
    try:
        os.link(backup, target)
    except OSError as exc:
        if exc.errno not in {errno.EPERM, errno.EACCES, errno.ENOSYS, errno.EOPNOTSUPP, errno.EXDEV, errno.EINVAL}:
            raise
        identity = _copy_exclusive(backup, target)
        try:
            current = target.lstat()
            if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
                identity.st_dev, identity.st_ino, identity.st_size, identity.st_mtime_ns
            ):
                raise FileExistsError(errno.EEXIST, "recovery target changed while restoring", str(target))
            shutil.copystat(backup, target)
        except BaseException:
            _safe_remove(target, identity)
            raise
    backup.unlink()


def _write_outputs(output_dir: Path, targets: dict[str, Path], artifacts: dict[str, str], overwrite: bool) -> None:
    staged: dict[str, Path] = {}
    backups: dict[str, Path] = {}
    installed: dict[str, os.stat_result] = {}
    try:
        for name in OUTPUT_NAMES:
            staged[name] = _stage_file(output_dir, artifacts[name])
        if overwrite:
            for name in OUTPUT_NAMES:
                target = targets[name]
                if not os.path.lexists(target):
                    continue
                fd, backup_name = tempfile.mkstemp(prefix=f".untangle-backup-{name}-", suffix=".tmp", dir=output_dir)
                os.close(fd)
                backup = Path(backup_name)
                backup.unlink()
                os.replace(target, backup)
                backups[name] = backup
        for name in OUTPUT_NAMES:
            installed[name] = _publish_no_clobber(staged[name], targets[name])
    except BaseException as exc:
        for name, identity in installed.items():
            _safe_remove(targets[name], identity)
        for name, backup in backups.items():
            if os.path.lexists(backup) and not os.path.lexists(targets[name]):
                with contextlib.suppress(OSError):
                    _restore_backup(backup, targets[name])
        retained = [f"{name} <- {backup}" for name, backup in backups.items() if os.path.lexists(backup)]
        recovery_note = "; retained recovery copies: " + "; ".join(retained) if retained else ""
        if isinstance(exc, OSError):
            raise FilesystemError(
                f"could not write outputs in '{output_dir}': {exc}{recovery_note}",
                context=f"output directory '{output_dir}'",
                hint="Check write permissions and free space; preserve any named recovery-copy paths.",
            ) from exc
        if recovery_note:
            print(f"render_map: interrupted{recovery_note}", file=sys.stderr)
        raise
    else:
        # Publication is committed. Disposing of old backups must never trigger rollback.
        try:
            for backup in backups.values():
                with contextlib.suppress(OSError):
                    backup.unlink(missing_ok=True)
        finally:
            retained = [f"{name} <- {backup}" for name, backup in backups.items() if os.path.lexists(backup)]
            if retained:
                print("render_map: outputs published; retained recovery copies: " + "; ".join(retained), file=sys.stderr)
    finally:
        for path in staged.values():
            with contextlib.suppress(OSError):
                path.unlink(missing_ok=True)


def _json_requested(argv: list[str]) -> bool:
    for argument in argv:
        if argument == "--":
            break
        option = argument.split("=", 1)[0]
        if option == "--json" or (len(option) > 2 and "--json".startswith(option)):
            return True
    return False


def _safe_argument_message(message: str) -> str:
    if "unrecognized arguments:" in message:
        extra = message.partition("unrecognized arguments:")[2].split()
        flags = [token.split("=", 1)[0] for token in extra if token.startswith("-")]
        if flags:
            return "unrecognized option(s): " + ", ".join(flags)
        return "unexpected extra positional argument"
    if "ignored explicit argument" in message:
        option = re.search(r"argument (--[A-Za-z0-9-]+)", message)
        return f"{option.group(1)} does not take a value" if option else "an option does not take a value"
    return message


def _argument_hint(message: str, argv: list[str], parser: argparse.ArgumentParser) -> str:
    if "--input" in argv:
        return "The manifest path is positional; use python render_map.py INPUT without --input."
    if "unrecognized arguments:" in message:
        extra = message.partition("unrecognized arguments:")[2].split()
        for token in extra:
            if token == "--input":
                return "The manifest path is positional; use python render_map.py INPUT without --input."
            if not token.startswith("-"):
                return "If the extra path is an output folder, pass it with --output-dir; --dry-run shows the three filenames."
            option = token.split("=", 1)[0]
            matches = difflib.get_close_matches(option, parser._option_string_actions, n=1, cutoff=0.58)
            if matches:
                return f"Use {matches[0]} instead of {option}; keep the remaining arguments unchanged."
    if "required: input" in message or "input manifest path is required" in message:
        return "Add the manifest as the positional input: python render_map.py PATH_TO_MANIFEST. Run python render_map.py --help for examples."
    expected_value = re.search(r"argument (--[A-Za-z0-9-]+): expected one argument", message)
    if expected_value:
        return f"Provide a value after {expected_value.group(1)}; run python render_map.py --help for examples."
    return "Run python render_map.py --help for valid options and examples."


def _emit_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True))


def _emit_cli_error(error: InputError, *, json_output: bool) -> None:
    print(f"render_map: error: {error}", file=sys.stderr)
    if error.context:
        print(f"  context: {error.context}", file=sys.stderr)
    if error.hint:
        print(f"  hint: {error.hint}", file=sys.stderr)
    if json_output:
        _emit_json({
            "schema_version": 1,
            "ok": False,
            "mode": "error",
            "error": {
                "code": error.code,
                "message": str(error),
                "context": error.context,
                "hint": error.hint,
            },
        })


def _renderer_parser() -> _RendererArgumentParser:
    epilog = """Examples:
  python render_map.py evidence.json --output-dir map-before
  python render_map.py evidence.json --check
  python render_map.py evidence.json --dry-run --output-dir map-after
  python render_map.py evidence.json --dry-run --overwrite --output-dir map-after
  python render_map.py evidence.json --json
  python render_map.py --schema

Exit status: 0 for success or help; 2 for input, argument, safety, or filesystem errors; 130 for cancellation.
--json writes one schema_version 1 result to stdout; diagnostics go to stderr.
--help always prints bounded text, including when --json is also present.
--schema prints the standalone JSON Schema for --json results and needs no input.
--check validates the input only; it does not render or create output paths.
--dry-run renders in memory and checks output safety without creating or writing files.
--overwrite is opt-in; --dry-run --overwrite previews replacement actions without replacing files."""
    parser = _RendererArgumentParser(
        prog="python render_map.py",
        description="Validate and render a standalone Untangle v1 wiring map.",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", nargs="?", help="UTF-8 JSON evidence manifest (positional)")
    parser.add_argument("--output-dir", default=None, help="output directory (default: current directory)")
    parser.add_argument("--overwrite", action="store_true", help="replace only untangle.html, comparison.svg and map.json")
    parser.add_argument("--check", "--validate-only", dest="check", action="store_true", help="validate input only; do not render or write files")
    parser.add_argument("--dry-run", action="store_true", help="validate and preview the three output paths without writing")
    parser.add_argument("--json", action="store_true", help="emit one versioned JSON result; errors keep diagnostics on stderr")
    parser.add_argument("--schema", action="store_true", help="print the JSON Schema for --json results without reading input")
    return parser


def _resolve_input_path(raw_input: str) -> Path:
    candidate = Path(raw_input)
    try:
        candidate = candidate.expanduser()
        input_path = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise FilesystemError(
            f"cannot access input file '{candidate}': {exc}",
            context=f"input file '{candidate}'",
            hint=f"Current directory is {Path.cwd()}; check the relative path or pass the input file's absolute path.",
        ) from exc
    if not input_path.is_file():
        raise InputError(
            f"input must be a regular file: '{input_path}'",
            context=f"input file '{input_path}'",
            hint="Pass the path to a regular UTF-8 JSON evidence manifest.",
        )
    return input_path


def _output_actions(targets: dict[str, Path]) -> list[dict[str, str]]:
    return [
        {"path": str(targets[name]), "action": "replace" if os.path.lexists(targets[name]) else "create"}
        for name in OUTPUT_NAMES
    ]


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    json_output = _json_requested(arguments)
    parser = _renderer_parser()
    try:
        args = parser.parse_args(arguments)
    except _ParserExit as exc:
        if exc.status == 0:
            sys.stdout.write(exc.message)
            return 0
        error = InputError(str(exc), code="argument_error", context="command line", hint="Run python render_map.py --help for valid options.")
        _emit_cli_error(error, json_output=json_output)
        return 2
    except _ArgumentFailure as exc:
        message = _safe_argument_message(str(exc))
        error = InputError(
            message,
            code="argument_error",
            context="command line",
            hint=_argument_hint(str(exc), arguments, parser),
        )
        _emit_cli_error(error, json_output=json_output)
        return 2

    if args.schema:
        conflicting = args.json or args.check or args.dry_run or args.overwrite or args.input is not None or args.output_dir is not None
        if conflicting:
            error = InputError(
                "--schema cannot be combined with an input, output, or operation flag",
                code="argument_error",
                context="command line",
                hint="Run python render_map.py --schema by itself; remove --json because the schema is already JSON.",
            )
            _emit_cli_error(error, json_output=json_output)
            return 2
        print(json.dumps(CLI_RESULT_SCHEMA, ensure_ascii=True, indent=2, sort_keys=True))
        return 0

    if args.check and args.dry_run:
        error = InputError(
            "--check and --dry-run are mutually exclusive",
            code="argument_error",
            context="command line",
            hint="Remove --dry-run to validate only, or remove --check to preview output paths.",
        )
        _emit_cli_error(error, json_output=json_output)
        return 2
    if args.check and (args.output_dir is not None or args.overwrite):
        error = InputError(
            "--check does not accept output options",
            code="argument_error",
            context="command line",
            hint="Remove --output-dir and --overwrite; --check reads only the input manifest.",
        )
        _emit_cli_error(error, json_output=json_output)
        return 2
    if args.input is None:
        error = InputError(
            "the input manifest path is required",
            code="argument_error",
            context="command line",
            hint="Add the manifest as the positional input: python render_map.py PATH_TO_MANIFEST. Run python render_map.py --help for examples.",
        )
        _emit_cli_error(error, json_output=json_output)
        return 2

    try:
        input_path = _resolve_input_path(args.input)
        data = _load_manifest(input_path)
        if args.check:
            if json_output:
                _emit_json({
                    "schema_version": 1,
                    "ok": True,
                    "mode": "check",
                    "result": {"input": str(input_path), "valid": True},
                })
            else:
                print(f"Valid input: {input_path}")
            return 0

        svg = render_svg(data)
        page = render_html(data, svg)
        normalized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        artifacts = {"untangle.html": page, "comparison.svg": svg + "\n", "map.json": normalized}
        raw_output_dir = args.output_dir if args.output_dir is not None else "."
        output_dir = _inspect_output_dir(raw_output_dir) if args.dry_run else _prepare_output_dir(raw_output_dir)
        targets = _check_output_targets(output_dir, input_path, args.overwrite)
        actions = _output_actions(targets)
        if args.dry_run:
            if json_output:
                _emit_json({
                    "schema_version": 1,
                    "ok": True,
                    "mode": "dry-run",
                    "result": {"input": str(input_path), "outputs": actions},
                })
            else:
                print("Plan (no files written):")
                for action in actions:
                    print(f"{action['action'].upper():7} {action['path']}")
            return 0

        _write_outputs(output_dir, targets, artifacts, args.overwrite)
    except InputError as exc:
        _emit_cli_error(exc, json_output=json_output)
        return 2
    except KeyboardInterrupt:
        error = InputError(
            "render cancelled",
            code="cancelled",
            context=f"input file '{args.input}', output directory '{args.output_dir or '.'}'",
            hint=(
                "Inspect the outputs and any reported recovery copies before retrying. "
                "Run python render_map.py --help for validation and dry-run commands."
            ),
        )
        _emit_cli_error(error, json_output=json_output)
        return 130
    except OSError as exc:
        error = FilesystemError(
            f"filesystem operation failed: {exc}",
            context="renderer input or output filesystem",
            hint="Check input/output path permissions and available space, then retry.",
        )
        _emit_cli_error(error, json_output=json_output)
        return 2
    except ValueError as exc:
        error = InputError(
            str(exc),
            context="renderer input or output",
            hint="Review the named input fields and output path, then retry.",
        )
        _emit_cli_error(error, json_output=json_output)
        return 2

    if json_output:
        _emit_json({
            "schema_version": 1,
            "ok": True,
            "mode": "render",
            "result": {"input": str(input_path), "outputs": actions},
        })
    else:
        print("Rendered: " + ", ".join(str(targets[name]) for name in OUTPUT_NAMES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
