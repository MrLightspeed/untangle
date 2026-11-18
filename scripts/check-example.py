"""Check the bundled before/after fixture and its renderer preview."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from html import escape
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/checkout"
TEST_RUNNER = FIXTURE / "tests/test_behavior.py"
RUNTIME_FILES = (
    "src/catalog.py",
    "src/orders.py",
    "src/quotes.py",
    "src/reconcile.py",
    "src/storage.py",
)
EXPECTED_PAIRS = {
    "before": {
        ("checkout", "src/orders.py"),
        ("checkout", "src/quotes.py"),
        ("checkout", "src/catalog.py"),
        ("checkout", "src/storage.py"),
        ("quote", "src/quotes.py"),
        ("quote", "src/orders.py"),
        ("quote", "src/storage.py"),
        ("quote", "src/catalog.py"),
        ("reconcile", "src/reconcile.py"),
        ("reconcile", "src/orders.py"),
        ("reconcile", "src/history.py"),
        ("reconcile", "src/storage.py"),
    },
    "after": {
        ("checkout", "src/orders.py"),
        ("checkout", "src/quotes.py"),
        ("checkout", "src/catalog.py"),
        ("checkout", "src/storage.py"),
        ("quote", "src/quotes.py"),
        ("quote", "src/catalog.py"),
        ("reconcile", "src/reconcile.py"),
        ("reconcile", "src/storage.py"),
    },
}
VERIFICATION_COMMAND = "python scripts/check-example.py"


def load_renderer():
    path = ROOT / "skills/untangle/scripts/render_map.py"
    spec = importlib.util.spec_from_file_location("render_map", path)
    if spec is None or spec.loader is None:
        raise SystemExit("Could not load the bundled map renderer.")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    return renderer


def fail(message: str) -> None:
    raise SystemExit(f"Example check failed: {message}")


def source_paths(snapshot_root: Path) -> list[Path]:
    found = sorted(path for path in snapshot_root.rglob("*.py") if path.is_file())
    actual = [path.relative_to(snapshot_root).as_posix() for path in found]
    expected = sorted((*RUNTIME_FILES, "src/history.py")) if snapshot_root.name == "before" else list(RUNTIME_FILES)
    if actual != expected:
        fail(f"{snapshot_root.name} runtime files differ from the fixture: {actual}")
    return found


def source_revision(snapshot_root: Path, paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(snapshot_root).as_posix().encode("utf-8")
        content = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def verify_locations(manifest: dict, snapshot_roots: dict[str, Path]) -> dict[str, str]:
    revisions = {}
    for snapshot_name, snapshot_root in snapshot_roots.items():
        snapshot = manifest[snapshot_name]
        paths = source_paths(snapshot_root)
        expected_files = [path.relative_to(snapshot_root).as_posix() for path in paths]
        if snapshot["files"] != expected_files:
            fail(f"{snapshot_name}.files does not match its complete runtime source inventory")
        actual_revision = source_revision(snapshot_root, paths)
        if snapshot["revision"] != actual_revision:
            fail(f"{snapshot_name}.revision is stale; expected {actual_revision}")
        revisions[snapshot_name] = actual_revision

        for edge in snapshot["edges"]:
            for evidence in edge["evidence"]:
                source = snapshot_root / evidence["path"]
                lines = source.read_text(encoding="utf-8").splitlines()
                line = evidence["line"]
                if line > len(lines) or not lines[line - 1].strip():
                    fail(
                        f"{snapshot_name} evidence points outside source or at a blank line: "
                        f"{evidence['path']}:{line}"
                    )

    baseline_root = snapshot_roots["before"]
    for knot in manifest["knots"]:
        for location in knot["locations"]:
            source = baseline_root / location["path"]
            lines = source.read_text(encoding="utf-8").splitlines()
            line = location["line"]
            if line > len(lines) or not lines[line - 1].strip():
                fail(f"Knot #{knot['id']} location is outside source or blank: {location}")

    return revisions


def verify_wiring(manifest: dict) -> int:
    pair_sets = {}
    for snapshot_name in ("before", "after"):
        pairs = {
            (edge["feature"], edge["file"])
            for edge in manifest[snapshot_name]["edges"]
        }
        if pairs != EXPECTED_PAIRS[snapshot_name]:
            fail(f"{snapshot_name} feature/file wiring does not match the fixture call graph")
        pair_sets[snapshot_name] = pairs
    return len(pair_sets["before"] | pair_sets["after"])


def verify_storage_ownership(snapshot_roots: dict[str, Path]) -> None:
    before_orders = (snapshot_roots["before"] / "src/orders.py").read_text(encoding="utf-8")
    before_reconcile = (snapshot_roots["before"] / "src/reconcile.py").read_text(encoding="utf-8")
    after_orders = (snapshot_roots["after"] / "src/orders.py").read_text(encoding="utf-8")
    after_reconcile = (snapshot_roots["after"] / "src/reconcile.py").read_text(encoding="utf-8")
    after_storage = (snapshot_roots["after"] / "src/storage.py").read_text(encoding="utf-8")

    if "json.dumps(order" not in before_orders or "json.loads(raw)" not in before_reconcile:
        fail("before callers must show the serialized-format ownership described by the knot")
    if "import json" in after_orders or "import json" in after_reconcile:
        fail("after callers must not import the JSON representation library")
    if "storage.write_order(order)" not in after_orders:
        fail("after order creation must use the storage owner's write_order operation")
    if "storage.read_orders()" not in after_reconcile:
        fail("after reconciliation must use the storage owner's read_orders operation")
    if "json.dumps(order" not in after_storage or "json.loads(raw)" not in after_storage:
        fail("after storage must own both JSON encoding and decoding")


def verify_comparison(manifest: dict, snapshot_roots: dict[str, Path]) -> None:
    expectations = {
        1: {
            "identities": (
                ("write-order", "Write an order"),
                ("read-pending-orders", "Read pending orders"),
            ),
            "endpoints": {
                "before": (
                    ((1, "Encode JSON"), (3, "Append bytes"), "JSON bytes"),
                    ((4, "Return raw rows"), (2, "Decode and filter"), "JSON bytes"),
                ),
                "after": (
                    ((1, "Pass order record"), (3, "Encode and append"), "Order record"),
                    ((4, "Decode stored rows"), (2, "Filter pending orders"), "Order records"),
                ),
            },
            "before_intermediates": ((), ((5, "History helper"), (6, "Order helper"))),
            "markers": {
                "before": (
                    ("src/orders.py", "json.dumps(order"),
                    ("src/orders.py", "storage.append(raw)"),
                    ("src/reconcile.py", "json.loads(raw)"),
                    ("src/reconcile.py", "_rows_for_reconciliation(storage)"),
                    ("src/orders.py", "read_raw_order_history(storage)"),
                    ("src/history.py", "storage.read_all()"),
                    ("src/storage.py", "self._rows.append(bytes(raw))"),
                    ("src/storage.py", "return tuple(self._rows)"),
                ),
                "after": (
                    ("src/orders.py", "storage.write_order(order)"),
                    ("src/reconcile.py", "storage.read_orders()"),
                    ("src/storage.py", "json.dumps(order"),
                    ("src/storage.py", "json.loads(raw)"),
                ),
            },
        },
        2: {
            "identities": (("price-lookup", "Look up a price"),),
            "endpoints": {
                "before": (
                    ((1, "Quote"), (4, "Catalog lookup"), "Product ID"),
                ),
                "after": (
                    ((1, "Quote"), (2, "Catalog lookup"), "Product ID"),
                ),
            },
            "before_intermediates": (((2, "Order helper"), (3, "Storage helper")),),
            "markers": {
                "before": (
                    ("src/quotes.py", "_order_unit_price(product_id)"),
                    ("src/orders.py", "_catalog_price_for(product_id)"),
                    ("src/storage.py", "price_for(product_id)"),
                    ("src/catalog.py", "PRICES[product_id]"),
                ),
                "after": (
                    ("src/quotes.py", "price_for(product_id)"),
                    ("src/catalog.py", "PRICES[product_id]"),
                ),
            },
        },
    }
    knots = {knot["id"]: knot for knot in manifest["knots"]}
    for knot_id, expected in expectations.items():
        if knot_id not in knots or not knots[knot_id].get("comparison"):
            fail(f"knot #{knot_id} must include its before/after source comparison")
        comparison = knots[knot_id]["comparison"]
        for phase in ("before", "after"):
            snippets = comparison[phase]["snippets"]
            paths = comparison[phase]["paths"]
            identities = tuple((path["id"], path["label"]) for path in paths)
            if identities != expected["identities"]:
                fail(f"knot #{knot_id} comparison {phase} has unexpected path labels")
            endpoints = tuple(
                (
                    (path["from"]["snippet"], path["from"]["label"]),
                    (path["to"]["snippet"], path["to"]["label"]),
                    path["value"],
                )
                for path in paths
            )
            if endpoints != expected["endpoints"][phase]:
                fail(f"knot #{knot_id} comparison {phase} has unexpected path endpoints")
            intermediates = tuple(tuple((node["snippet"], node["label"]) for node in path.get("via", [])) for path in paths)
            expected_intermediates = expected["before_intermediates"] if phase == "before" else tuple(() for _ in paths)
            if intermediates != expected_intermediates:
                fail(f"knot #{knot_id} comparison {phase} has unexpected intermediate owners")
            for snippet in snippets:
                source_lines = (
                    (snapshot_roots[phase] / snippet["path"])
                    .read_text(encoding="utf-8")
                    .splitlines()
                )
                excerpt = snippet["code"].splitlines()
                start = snippet["line"] - 1
                if source_lines[start : start + len(excerpt)] != excerpt:
                    fail(
                        f"knot #{knot_id} comparison excerpt does not match {phase} "
                        f"source at {snippet['path']}:{snippet['line']}"
                    )
            for relative_path, marker in expected["markers"][phase]:
                if not any(
                    snippet["path"] == relative_path and marker in snippet["code"]
                    for snippet in snippets
                ):
                    fail(
                        f"knot #{knot_id} comparison {phase} is missing {marker} "
                        f"in {relative_path}"
                    )


def verify_fixed_knots(manifest: dict) -> None:
    if manifest["after"] is None:
        fail("the worked example needs an actual after snapshot")
    knots = {knot["id"]: knot for knot in manifest["knots"]}
    if set(knots) != {1, 2}:
        fail("the worked example must record exactly knots #1 and #2")
    expected = {
        "tests": {"kind": "tests", "command": VERIFICATION_COMMAND, "result": "pass"},
        "build": {"kind": "build", "command": VERIFICATION_COMMAND, "result": "pass"},
    }
    for knot_id, knot in knots.items():
        if knot["status"] != "fixed":
            fail(f"knot #{knot_id} must be recorded as fixed")
        actual = {check["kind"]: check for check in knot["verification"]}
        for kind, record in expected.items():
            if (
                actual.get(kind, {}).get("command") != record["command"]
                or actual.get(kind, {}).get("result") != record["result"]
            ):
                fail(
                    f"knot #{knot_id} must record passing tests and build checks "
                    "from the checker command"
                )


def compile_snapshot(snapshot_root: Path) -> None:
    for path in source_paths(snapshot_root):
        content = path.read_text(encoding="utf-8")
        compile(content, path.as_posix(), "exec")


def report(message: str, json_mode: bool) -> None:
    stream = sys.stderr if json_mode else sys.stdout
    print(message, file=stream)


def run_behavior_checks(snapshot_roots: dict[str, Path], json_mode: bool) -> None:
    for snapshot_name, snapshot_root in snapshot_roots.items():
        try:
            completed = subprocess.run(
                [sys.executable, "-B", str(TEST_RUNNER), "--snapshot", str(snapshot_root)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            fail(f"{snapshot_name} behavior checks exceeded 60 seconds; inspect the snapshot tests.")
        if completed.returncode != 0:
            output = (completed.stdout + completed.stderr).strip()
            fail(f"{snapshot_name} behavior checks failed.\n{output}")
        summary = (completed.stdout + completed.stderr).strip().splitlines()
        result_line = next(
            (line for line in reversed(summary) if line.startswith("Ran ")),
            "checks passed",
        )
        report(f"{snapshot_name}: {result_line}", json_mode)


def render_checkout_preview(renderer, price_knot: dict, storage_knot: dict) -> str:
    """Lay out the two checked checkout routes on a shared set of file positions."""
    routes = (
        (price_knot, "price-lookup", "#ffb779"),
        (storage_knot, "read-pending-orders", "#78e4d4"),
    )
    positions = {
        "quotes.py": (82, 155),
        "catalog.py": (414, 155),
        "history.py": (238, 215),
        "orders.py": (260, 298),
        "storage.py": (82, 370),
        "reconcile.py": (414, 370),
    }
    # Layout for this fixture only. Keys bind geometry to actual handoffs.
    wire_paths = {
        ("quotes.py", "orders.py"): "M148 155 C377 144 387 239 290 276",
        ("orders.py", "storage.py"): "M194 301 C166 301 159 324 130 348",
        ("storage.py", "catalog.py"): "M148 374 C235 435 361 416 414 177",
        ("storage.py", "history.py"): "M68 348 C68 268 110 213 172 215",
        ("history.py", "orders.py"): "M220 237 C220 258 222 267 222 276",
        ("orders.py", "reconcile.py"): "M326 301 C333 326 336 353 348 371",
        ("quotes.py", "catalog.py"): "M148 155 H348",
        ("storage.py", "reconcile.py"): "M148 370 H348",
    }
    text = renderer._svg_text
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1034" height="508" '
        'viewBox="0 0 1034 508" role="img" aria-labelledby="title description">',
        '<title id="title">Checkout wiring before and after</title>',
        '<desc id="description">Quotes and pending orders each go from three '
        'source handoffs to one. File positions stay fixed. '
        'Storage now decodes JSON before sending order records to reconciliation.</desc>',
        '<rect width="1034" height="508" rx="18" fill="#0b1220"/>',
        text(27, 42, "Two checkout detours become direct", 29, "#f2f6fb", "700"),
        '<defs>',
    ]
    for _, route_id, color in routes:
        parts.append(
            f'<marker id="{route_id}" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="3.7" markerHeight="3.7" orient="auto">'
            f'<path d="M0 0 L10 5 L0 10 Z" fill="{color}"/></marker>'
        )
    parts.append('</defs>')

    for phase, offset in (("before", 13), ("after", 521)):
        parts.append(f'<g data-phase="{phase}" transform="translate({offset} 62)">')
        parts.append('<rect width="500" height="407" rx="14" fill="#101c2d" stroke="#364a62"/>')
        parts.append(text(20, 37, phase.title(), 26, "#f2f6fb", "700"))
        active: dict[str, list[str]] = {}
        for index, (knot, route_id, color) in enumerate(routes):
            side = knot["comparison"][phase]
            path = next(path for path in side["paths"] if path["id"] == route_id)
            nodes = []
            for node in renderer._path_nodes(path):
                location = renderer._path_location(node, side)
                owner = Path(side["snippets"][node["snippet"] - 1]["path"]).name
                nodes.append(owner)
                active.setdefault(owner, []).append(location)
            value = path["value"]
            count = len(nodes) - 1
            unit = "handoff" if count == 1 else "handoffs"
            legend = f'{path["label"]} · {value} · {count} {unit}'
            parts.append(text(20, 70 + index * 25, legend, 18, color, "600"))
            for source, target in zip(nodes, nodes[1:]):
                geometry = wire_paths.get((source, target))
                if geometry is None:
                    fail(f"checkout preview has no layout for {source} to {target}")
                parts.append(
                    f'<path d="{geometry}" fill="none" stroke="#101c2d" stroke-width="11"/>'
                )
                parts.append(
                    f'<path data-route="{route_id}" data-from="{escape(source)}" '
                    f'data-to="{escape(target)}" d="{geometry}" fill="none" '
                    f'stroke="{color}" stroke-width="4" marker-end="url(#{route_id})"/>'
                )
        for owner, (x, y) in positions.items():
            refs = active.get(owner)
            status = "On a shown route" if refs else "Outside the shown routes"
            detail = ", ".join(refs) if refs else status
            outline = '#7389a3' if refs else '#5e718a'
            dash = '' if refs else ' stroke-dasharray="5 5"'
            parts.extend([
                f'<g data-file="{owner}"><title>{escape(detail)}</title>',
                f'<rect x="{x - 66}" y="{y - 22}" width="132" height="44" rx="8" '
                f'fill="#0b1220" stroke="{outline}"{dash}/>',
                text(x, y + 6, owner, 18, "#f2f6fb" if refs else "#adbed2",
                     "600", 'text-anchor="middle"'),
                '</g>',
            ])
        if phase == "after":
            parts.append(text(249, 261, "Dashed files are outside these routes", 15,
                              "#adbed2", extra='text-anchor="middle"'))
        parts.append('</g>')

    parts.append(text(27, 490, "Storage now decodes the rows, so reconciliation receives order records.", 21))
    return "\n".join([*parts, "</svg>"])


class ContributorArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(
            f"{self.prog}: error: {message}\n"
            "Try: python scripts/check-example.py --help",
            file=sys.stderr,
        )
        raise SystemExit(2)


class ExampleCheckError(Exception):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def parser() -> argparse.ArgumentParser:
    result = ContributorArgumentParser(
        description=__doc__,
        allow_abbrev=False,
        epilog=(
            "Commands: python scripts/check-example.py; regenerate the preview with "
            "python scripts/check-example.py --write-preview.\n"
            "Exit codes: 0 checks passed; 1 check failed; 2 invalid arguments."
        ),
    )
    result.add_argument(
        "--write-preview",
        action="store_true",
        help="regenerate the checked-in SVGs from the validated manifest",
    )
    result.add_argument(
        "--json",
        action="store_true",
        help="emit one versioned result; progress and diagnostics go to stderr",
    )
    return result


def run_checks(args: argparse.Namespace) -> dict:
    stage = "Python runtime check"
    try:
        if sys.version_info < (3, 13):
            fail("Python 3.13 or newer is required")

        stage = "evidence manifest and renderer validation"
        raw_manifest = json.loads((ROOT / "examples/evidence.json").read_text(encoding="utf-8"))
        renderer = load_renderer()
        manifest = renderer.validate_manifest(raw_manifest)
        snapshot_roots = {
            "before": FIXTURE / "before",
            "after": FIXTURE / "after",
        }
        stage = "source inventory and evidence references"
        source_revisions = verify_locations(raw_manifest, snapshot_roots)
        stage = "before/after comparison source excerpts"
        verify_comparison(manifest, snapshot_roots)
        stage = "feature wiring and ownership checks"
        feature_file_pairs_checked = verify_wiring(manifest)
        verify_storage_ownership(snapshot_roots)
        verify_fixed_knots(manifest)

        stage = "source compilation and behavior tests"
        for snapshot_root in snapshot_roots.values():
            compile_snapshot(snapshot_root)
        run_behavior_checks(snapshot_roots, args.json)

        stage = "renderer preview validation"
        storage_knot = next(knot for knot in manifest["knots"] if knot["id"] == 1)
        price_knot = next(knot for knot in manifest["knots"] if knot["id"] == 2)
        previews = {
            "example-comparison.svg": renderer.render_svg(manifest) + "\n",
            "example-price-route.svg": renderer.render_path_comparison_svg(price_knot, "price-lookup") + "\n",
            "untangle-banner.svg": renderer.render_knot_routes_svg(storage_knot, ("read-pending-orders", "write-order")) + "\n",
            "example-checkout-wiring.svg": render_checkout_preview(renderer, price_knot, storage_knot) + "\n",
        }
        for name, preview in previews.items():
            preview_path = ROOT / "assets" / name
            if args.write_preview:
                preview_path.write_text(preview, encoding="utf-8", newline="\n")
                report(f"Updated {preview_path.relative_to(ROOT).as_posix()}.", args.json)
            elif not preview_path.is_file() or preview_path.read_text(encoding="utf-8") != preview:
                fail(f"assets/{name} is stale; run python scripts/check-example.py --write-preview")

        capture = json.loads((ROOT / "examples/preview-capture.json").read_text(encoding="utf-8"))
        expected_capture = {
            "svg_sha256": hashlib.sha256(previews["example-price-route.svg"].encode("utf-8")).hexdigest(),
            "png_sha256": hashlib.sha256((ROOT / "assets/untangle-before-after.png").read_bytes()).hexdigest(),
        }
        if capture != expected_capture:
            fail("The price-route PNG or its source SVG differs from the recorded capture. "
                 "See examples/README.md to refresh the PNG and its record.")

        report(
            f"Source hashes and evidence references match; checks used Python {sys.version.split()[0]}.",
            args.json,
        )
        report(
            f"Feature/file wiring has {len(EXPECTED_PAIRS['before'])} pairs before and "
            f"{len(EXPECTED_PAIRS['after'])} after ({feature_file_pairs_checked} unique pairs); "
            "renderer preview is current.",
            args.json,
        )
        return {
            "schema_version": "1.0.0",
            "command": "check-example",
            "status": "passed",
            "python_version": sys.version.split()[0],
            "source_revisions": source_revisions,
            "feature_file_pairs_checked": feature_file_pairs_checked,
            "preview_updated": args.write_preview,
        }
    except SystemExit as error:
        if isinstance(error.code, str):
            message = error.code
        else:
            message = "the example check exited unexpectedly"
        if message.startswith("Example check failed: "):
            message = message.removeprefix("Example check failed: ")
        raise ExampleCheckError(stage, message) from None
    except Exception as error:
        message = str(error).splitlines()[0] if str(error) else type(error).__name__
        raise ExampleCheckError(stage, message[:400]) from None


def main() -> int:
    args = parser().parse_args()
    try:
        result = run_checks(args)
    except ExampleCheckError as error:
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "command": "check-example",
                        "status": "failed",
                        "error": {
                            "stage": error.stage,
                            "message": str(error),
                            "recovery": "python scripts/check-example.py --help",
                        },
                    },
                    sort_keys=True,
                )
            )
        else:
            print(f"Example check failed during {error.stage}: {error}", file=sys.stderr)
            print("Try: python scripts/check-example.py --help", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
