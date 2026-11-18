"""Focused tests for source-based explanations in wiring-map comparisons.

Behavior owner: skills/untangle/scripts/render_map.py validation and rendering.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location(
    "render_map",
    Path(__file__).resolve().parents[1] / "skills/untangle/scripts/render_map.py",
)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def comparison(index: int = 1) -> dict[str, object]:
    return {
        "before": {
            "summary": f"Callers handle JSON conversion {index}.",
            "snippets": [
                {
                    "path": "source/orders.py",
                    "line": 2,
                    "code": "encoded = json.dumps(order)",
                },
                {
                    "path": "source/reconcile.py",
                    "line": 4,
                    "code": "order = json.loads(raw)",
                },
            ],
        },
        "after": {
            "summary": f"Storage owns JSON conversion {index}.",
            "snippets": [
                {
                    "path": "source/orders.py",
                    "line": 3,
                    "code": "storage.write_order(order)",
                },
                {
                    "path": "source/reconcile.py",
                    "line": 5,
                    "code": "storage.read_orders()",
                },
                {
                    "path": "source/storage.py",
                    "line": 2,
                    "code": "encoded = json.dumps(order)",
                },
            ],
        },
        "benefit": "Order callers no longer know how records are stored.",
        "preserved": "Calls, stored bytes, errors, and feature/file pairs stay the same.",
    }


def path_record(index: int = 1) -> dict[str, object]:
    return {
        "id": f"order-flow-{index}",
        "label": f"Persist order record {index}",
        "from": {"snippet": 1, "label": "Order object"},
        "to": {"snippet": 3, "label": "Stored record"},
        "value": "Serialized order JSON bytes",
    }


def with_paths(raw: dict[str, object], count: int = 1) -> dict[str, object]:
    comparison_record = raw["knots"][0]["comparison"]
    comparison_record["before"]["snippets"].append(
        {
            "path": "source/storage.py",
            "line": 10,
            "code": "write_bytes(encoded)",
        }
    )
    comparison_record["before"]["paths"] = [path_record(index) for index in range(1, count + 1)]
    comparison_record["after"]["paths"] = [path_record(index) for index in range(1, count + 1)]
    return raw


def manifest() -> dict[str, object]:
    files = [
        "source/orders.py",
        "source/reconcile.py",
        "source/storage.py",
        "source/catalog.py",
    ]
    edge = {
        "feature": "checkout",
        "file": "source/orders.py",
        "evidence": [
            {
                "path": "source/orders.py",
                "line": 2,
                "note": "Order entry point calls storage.",
                "kind": "direct",
            }
        ],
    }
    reconcile_edge = {
        "feature": "checkout",
        "file": "source/reconcile.py",
        "evidence": [
            {
                "path": "source/reconcile.py",
                "line": 4,
                "note": "Pending-order entry point calls storage.",
                "kind": "direct",
            }
        ],
    }
    knot = {
        "id": 1,
        "category": "leaky-abstraction",
        "severity": "medium",
        "title": "Callers own the stored format",
        "features": ["checkout"],
        "locations": [{"path": "source/orders.py", "line": 2}],
        "evidence": "The order and reconciliation callers convert JSON.",
        "remedy": "Move JSON conversion into the storage owner.",
        "status": "open",
        "verification": [],
        "comparison": comparison(),
    }
    return {
        "schema_version": 1,
        "title": "Storage ownership example",
        "scope": "Order creation and pending-order reconciliation.",
        "features": [{"id": "checkout", "label": "Place an order"}],
        "knots": [knot],
        "before": {
            "revision": "fixture-before",
            "coverage": "The fixture traces the checkout entry point.",
            "files": files,
            "edges": [copy.deepcopy(edge), copy.deepcopy(reconcile_edge)],
        },
        "after": {
            "revision": "fixture-after",
            "coverage": "The fixture traces the same checkout entry point.",
            "files": files,
            "edges": [copy.deepcopy(edge), copy.deepcopy(reconcile_edge)],
        },
    }


def route_comparison_manifest(via_phase: str = "before") -> dict[str, object]:
    """Build a small route fixture for testing full-render embedding."""
    if via_phase not in {"before", "after"}:
        raise ValueError("via_phase must be before or after")

    raw = manifest()
    route_files = [
        "source/quotes.py",
        "source/orders-route.py",
        "source/storage-route.py",
        "source/catalog-route.py",
    ]
    for phase in ("before", "after"):
        raw[phase]["files"] = list(dict.fromkeys([*raw[phase]["files"], *route_files]))

    knot = raw["knots"][0]
    knot["id"] = 2
    knot["title"] = "Quote price lookup route"
    comparison_record = knot["comparison"]
    route_path = {
        "id": "price-lookup",
        "label": "Look up a price",
        "from": {"snippet": 1, "label": "Quote price request"},
        "via": [
            {"snippet": 2, "label": "Order price helper"},
            {"snippet": 3, "label": "Storage price helper"},
        ],
        "to": {"snippet": 4, "label": "Catalog price lookup"},
        "value": "Product ID",
    }
    direct_path = {
        "id": "price-lookup",
        "label": "Look up a price",
        "from": {"snippet": 1, "label": "Quote price request"},
        "to": {"snippet": 2, "label": "Catalog price lookup"},
        "value": "Product ID",
    }
    direct_snippets = {
        "before": [
            {"path": route_files[0], "line": 7, "code": "quote_price(product_id)"},
            {"path": route_files[3], "line": 10, "code": "catalog_price(product_id)"},
        ],
        "after": [
            {"path": route_files[0], "line": 11, "code": "catalog_price(product_id)"},
            {"path": route_files[3], "line": 12, "code": "return prices[product_id]"},
        ],
    }
    via_snippets = {
        "before": [
            {"path": route_files[0], "line": 7, "code": "quote_price(product_id)"},
            {"path": route_files[1], "line": 8, "code": "order_price(product_id)"},
            {"path": route_files[2], "line": 9, "code": "storage_price(product_id)"},
            {"path": route_files[3], "line": 10, "code": "catalog_price(product_id)"},
        ],
        "after": [
            {"path": route_files[0], "line": 11, "code": "quote_price(product_id)"},
            {"path": route_files[1], "line": 12, "code": "order_price(product_id)"},
            {"path": route_files[2], "line": 13, "code": "storage_price(product_id)"},
            {"path": route_files[3], "line": 14, "code": "return prices[product_id]"},
        ],
    }
    for phase in ("before", "after"):
        has_via = phase == via_phase
        comparison_record[phase]["snippets"] = copy.deepcopy(
            via_snippets[phase] if has_via else direct_snippets[phase]
        )
        comparison_record[phase]["paths"] = [
            copy.deepcopy(route_path if has_via else direct_path)
        ]
    return raw


def example_manifest() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / "examples/evidence.json").read_text(encoding="utf-8"))


def svg_text(svg: str) -> str:
    root = ET.fromstring(svg)
    return " ".join(" ".join(text for text in root.itertext() if text).split())


SVG_NS = "http://www.w3.org/2000/svg"


def elements_by_class(root: ET.Element, tag: str, class_name: str) -> list[ET.Element]:
    return [
        element
        for element in root.iter(f"{{{SVG_NS}}}{tag}")
        if element.get("class") == class_name
    ]


def route_phases(root: ET.Element) -> dict[str, ET.Element]:
    return {
        phase.get("data-phase", ""): phase
        for phase in elements_by_class(root, "g", "route-phase")
    }


def snapshot_panels(root: ET.Element) -> tuple[ET.Element, ET.Element]:
    panels = [
        element
        for element in root.iter(f"{{{SVG_NS}}}g")
        if element.get("class") == "snapshot-panel"
    ]
    before = next(panel for panel in panels if panel.get("aria-label", "").lower().startswith("before"))
    after = next(panel for panel in panels if panel.get("aria-label", "").lower().startswith("after"))
    return before, after


def panel_routes(panel: ET.Element) -> dict[tuple[str, str], ET.Element]:
    file_names = {
        group.get("data-file-group-index"): group.findtext(f"{{{SVG_NS}}}title")
        for group in panel.iter(f"{{{SVG_NS}}}g")
        if group.get("class") == "diagram-file"
    }
    return {
        (edge.get("data-feature-index", ""), file_names[edge.get("data-file-group-index")]): edge
        for edge in panel.iter(f"{{{SVG_NS}}}path")
        if edge.get("class") == "edge"
    }


def html_overview_svg(page: str) -> str:
    figure_start = page.index("<figure")
    svg_start = page.index('<svg class="comparison"', figure_start)
    svg_end = page.index("</svg>", svg_start) + len("</svg>")
    return page[svg_start:svg_end]


class RenderComparisonTests(unittest.TestCase):
    def test_overview_distinguishes_files_in_the_same_long_directory(self):
        raw = manifest()
        directory = "scripts/same_long_directory/"
        names = ["find_quote.py", "post_order.py"]
        for phase in ("before", "after"):
            raw[phase] = {
                **raw[phase],
                "files": [directory + name for name in names],
                "edges": [],
            }
        raw["knots"] = []

        overview = ET.fromstring(renderer.render_wiring_svg(renderer.validate_manifest(raw)))
        for panel in snapshot_panels(overview):
            file_nodes = elements_by_class(panel, "g", "diagram-file")
            titles = {node.findtext(f"{{{SVG_NS}}}title") for node in file_nodes}
            labels = {node.findtext(f"{{{SVG_NS}}}text") for node in file_nodes}
            self.assertEqual(titles, {directory + name for name in names})
            self.assertEqual(labels, set(names))

    def test_fixed_status_does_not_recolor_data_flow_arrows(self):
        raw = with_paths(manifest())
        knot = raw["knots"][0]
        knot["status"] = "fixed"
        knot["verification"] = [
            {"kind": kind, "command": "fixture check", "result": "pass"}
            for kind in ("tests", "build")
        ]
        data = renderer.validate_manifest(raw)
        svg = renderer.render_svg(data)
        root = ET.fromstring(svg)
        flow_strokes = {
            path.get("stroke") for path in root.findall(f".//{{{SVG_NS}}}path")
            if path.get("class") != "edge"
        }
        self.assertEqual(len(flow_strokes), 1)
        self.assertNotIn("#7be3af", flow_strokes)
        self.assertNotIn("#278355", flow_strokes)
        fixed_badges = root.findall(f'.//{{{SVG_NS}}}g[@class="svg-knot-badge"]/{{{SVG_NS}}}rect')
        self.assertTrue(any(rect.get("fill") == "#278355" for rect in fixed_badges))
        self.assertIn("renderer does not run", svg_text(svg))

    def test_path_image_keeps_distinguishable_long_locations_without_hover(self):
        raw = with_paths(manifest())
        replacements = {
            "source/orders.py": "src/checkout/workflows/invoice_orders.py",
            "source/storage.py": "src/checkout/workflows/inventory_orders.py",
        }
        for phase in ("before", "after"):
            snapshot = raw[phase]
            snapshot["files"] = [replacements.get(path, path) for path in snapshot["files"]]
            for edge in snapshot["edges"]:
                edge["file"] = replacements.get(edge["file"], edge["file"])
                for evidence in edge["evidence"]:
                    evidence["path"] = replacements.get(evidence["path"], evidence["path"])
            snippets = raw["knots"][0]["comparison"][phase]["snippets"]
            for snippet in snippets:
                snippet["path"] = replacements.get(snippet["path"], snippet["path"])
            snippets[0]["line"] = 123
            snippets[2]["line"] = 456
        data = renderer.validate_manifest(raw)
        svg = ET.fromstring(renderer.render_svg(data))
        visible_text = "".join(element.text or "" for element in svg.findall(".//{http://www.w3.org/2000/svg}text"))
        self.assertIn("src/checkout/workflows/invoice_orders.py:123", visible_text)
        self.assertIn("src/checkout/workflows/inventory_orders.py:456", visible_text)

    def test_example_checker_rejects_changed_text_and_missing_callsites(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("check_example", root / "scripts/check-example.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        example = json.loads((root / "examples/evidence.json").read_text(encoding="utf-8"))
        snapshots = {phase: root / "examples/checkout" / phase for phase in ("before", "after")}
        for failure in ("changed source excerpt", "missing storage decoding"):
            with self.subTest(failure=failure):
                raw = copy.deepcopy(example)
                excerpts = raw["knots"][0]["comparison"]
                if failure == "changed source excerpt":
                    excerpts["before"]["snippets"][0]["code"] += " # not in source"
                else:
                    excerpts["after"]["snippets"][3]["code"] = "yield order"
                data = renderer.validate_manifest(raw)
                with self.assertRaises(SystemExit):
                    checker.verify_comparison(data, snapshots)

    # Behavior owner: check-example.py verifies each supplied intermediate snippet reference.
    def test_example_checker_rejects_reordered_or_missing_intermediate_refs(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("check_example", root / "scripts/check-example.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        raw = example_manifest()
        snapshots = {phase: root / "examples/checkout" / phase for phase in ("before", "after")}

        checker.verify_comparison(renderer.validate_manifest(raw), snapshots)
        before_path = next(knot for knot in raw["knots"] if knot["id"] == 2)["comparison"]["before"]["paths"][0]
        self.assertEqual([node["snippet"] for node in before_path["via"]], [2, 3])

        for failure in ("reordered intermediate refs", "missing intermediate refs"):
            with self.subTest(failure=failure):
                mutated = copy.deepcopy(raw)
                path = next(knot for knot in mutated["knots"] if knot["id"] == 2)["comparison"]["before"]["paths"][0]
                if failure == "reordered intermediate refs":
                    path["via"][0]["snippet"], path["via"][1]["snippet"] = (
                        path["via"][1]["snippet"],
                        path["via"][0]["snippet"],
                    )
                else:
                    path.pop("via")
                data = renderer.validate_manifest(mutated)
                with self.assertRaises(SystemExit):
                    checker.verify_comparison(data, snapshots)

    # Behavior owner: validate_manifest keeps schema-v1 manifests compatible.
    def test_legacy_manifest_without_comparison_remains_valid(self):
        raw = manifest()
        raw["knots"][0].pop("comparison")

        data = renderer.validate_manifest(raw)

        self.assertNotIn("comparison", data["knots"][0])
        rendered = renderer.render_svg(data)
        self.assertIn("Storage ownership example", svg_text(rendered))
        self.assertIn("No source change explanations supplied", svg_text(rendered))

    # Behavior owner: validate_manifest checks comparison shape and path bounds.
    def test_comparison_requires_an_after_snapshot(self):
        raw = manifest()
        raw["after"] = None

        with self.assertRaises(renderer.InputError):
            renderer.validate_manifest(raw)

    # Behavior owner: validate_manifest rejects malformed comparison records.
    def test_comparison_rejects_bad_paths_lines_and_bounds(self):
        cases = (
            ("missing after side", lambda value: value.pop("after")),
            ("missing benefit", lambda value: value.pop("benefit")),
            ("unknown comparison field", lambda value: value.update(extra="not allowed")),
            ("empty before snippets", lambda value: value["before"].update(snippets=[])),
            ("missing snippet code", lambda value: value["after"]["snippets"][0].pop("code")),
            ("unknown before path", lambda value: value["before"]["snippets"][0].update(path="source/missing.py")),
            ("unknown after path", lambda value: value["after"]["snippets"][0].update(path="source/missing.py")),
            ("zero line", lambda value: value["before"]["snippets"][0].update(line=0)),
            ("too many snippets", lambda value: value["before"].update(snippets=[{"path": "source/orders.py", "line": 1, "code": "x"}] * 7)),
            ("too many lines", lambda value: value["after"]["snippets"][0].update(code="\n".join(["x"] * 13))),
            ("oversized code", lambda value: value["after"]["snippets"][0].update(code="x" * 1001)),
            ("oversized summary", lambda value: value["before"].update(summary="x" * 401)),
            ("oversized benefit", lambda value: value.update(benefit="x" * 701)),
            ("oversized preserved behavior", lambda value: value.update(preserved="x" * 701)),
        )
        for label, mutate in cases:
            with self.subTest(case=label):
                raw = manifest()
                mutate(raw["knots"][0]["comparison"])
                with self.assertRaises(renderer.InputError):
                    renderer.validate_manifest(raw)

    # Behavior owner: render_svg and render_html show the supplied source change.
    def test_comparison_shows_before_after_benefit_and_unchanged_wiring(self):
        data = renderer.validate_manifest(manifest())

        svg = renderer.render_svg(data)
        page = renderer.render_html(data, svg)
        text = svg_text(svg)

        content = (
            "Callers handle JSON conversion 1.",
            "encoded = json.dumps(order)",
            "storage.write_order(order)",
            "Storage owns JSON conversion 1.",
            "source/orders.py:2",
            "source/storage.py:2",
            "Order callers no longer know how records are stored.",
            "Calls, stored bytes, errors, and feature/file pairs stay the same.",
            "unchanged",
        )
        for value in content:
            with self.subTest(content=value):
                self.assertIn(value, text)
                self.assertIn(value, page)
        self.assertIn("open", text)

    # Behavior owner: computed wiring deltas describe the snapshots accurately.
    def test_comparison_reports_a_real_feature_file_pair_change(self):
        raw = manifest()
        raw["after"]["edges"][0]["file"] = "source/storage.py"
        raw["after"]["edges"][0]["evidence"][0]["path"] = "source/storage.py"
        data = renderer.validate_manifest(raw)

        text = svg_text(renderer.render_svg(data)).lower()

        self.assertIn("1 retained", text)
        self.assertIn("1 added", text)
        self.assertIn("1 removed", text)
        self.assertNotIn("connections unchanged", text)

    # Behavior owner: validate_manifest keeps paired path identities in phase order.
    def test_paired_paths_require_matching_ids_order_and_labels(self):
        cases = (
            (
                "mismatched id",
                lambda before, after: after[0].update(id="different-flow"),
            ),
            (
                "mismatched order",
                lambda before, after: after.reverse(),
            ),
            (
                "mismatched label",
                lambda before, after: after[0].update(label="Different label"),
            ),
        )
        for label, mutate in cases:
            with self.subTest(case=label):
                raw = with_paths(manifest(), count=2)
                before = raw["knots"][0]["comparison"]["before"]["paths"]
                after = raw["knots"][0]["comparison"]["after"]["paths"]
                mutate(before, after)
                with self.assertRaises(renderer.InputError):
                    renderer.validate_manifest(raw)

    # Behavior owner: validate_manifest bounds and links path endpoints to excerpts.
    def test_comparison_paths_reject_dangling_refs_and_malformed_records(self):
        cases = (
            ("zero snippet ref", "before", lambda path: path["from"].update(snippet=0)),
            ("boolean snippet ref", "after", lambda path: path["to"].update(snippet=True)),
            ("dangling before snippet ref", "before", lambda path: path["from"].update(snippet=4)),
            ("dangling after snippet ref", "after", lambda path: path["to"].update(snippet=4)),
            ("missing path label", "before", lambda path: path.pop("label")),
            ("empty path id", "before", lambda path: path.update(id="")),
            ("empty path label", "before", lambda path: path.update(label="")),
            ("empty endpoint label", "before", lambda path: path["from"].update(label="")),
            ("empty value", "before", lambda path: path.update(value="")),
            ("unknown path field", "after", lambda path: path.update(extra="not allowed")),
            ("unknown endpoint field", "before", lambda path: path["from"].update(extra="not allowed")),
            ("missing endpoint snippet", "after", lambda path: path["to"].pop("snippet")),
            ("oversized path id", "before", lambda path: path.update(id="x" * 81)),
            ("oversized path label", "before", lambda path: path.update(label="x" * 121)),
            ("oversized endpoint label", "before", lambda path: path["from"].update(label="x" * 121)),
            ("oversized value", "before", lambda path: path.update(value="x" * 101)),
            ("duplicate ids", "before", lambda path: path.update(id="order-flow-2")),
        )
        for label, phase, mutate in cases:
            with self.subTest(case=label):
                raw = with_paths(manifest(), count=2)
                paths = raw["knots"][0]["comparison"][phase]["paths"]
                mutate(paths[0])
                with self.assertRaises(renderer.InputError):
                    renderer.validate_manifest(raw)

    # Behavior owner: validate_manifest caps each phase at four source paths.
    def test_comparison_paths_allow_four_but_reject_five(self):
        renderer.validate_manifest(with_paths(manifest(), count=4))

        with self.assertRaises(renderer.InputError):
            renderer.validate_manifest(with_paths(manifest(), count=5))

    # Behavior owner: validate_manifest requires paths in both phases or neither.
    def test_comparison_paths_must_be_present_in_both_phases(self):
        for missing_phase in ("before", "after"):
            with self.subTest(phase=missing_phase):
                raw = with_paths(manifest())
                raw["knots"][0]["comparison"][missing_phase].pop("paths")

                with self.assertRaises(renderer.InputError):
                    renderer.validate_manifest(raw)

    # Behavior owner: schema-v1 paths without an optional via chain remain valid.
    def test_legacy_paired_paths_without_via_remain_valid(self):
        data = renderer.validate_manifest(with_paths(manifest()))

        for phase in ("before", "after"):
            with self.subTest(phase=phase):
                self.assertNotIn("via", data["knots"][0]["comparison"][phase]["paths"][0])

    # Behavior owner: validate_manifest bounds optional via endpoints and source owners.
    def test_comparison_paths_reject_malformed_via_chains(self):
        valid_node = {"snippet": 2, "label": "Reconciliation helper"}
        cases = (
            ("empty via", lambda path: path.update(via=[])),
            (
                "three via nodes",
                lambda path: path.update(
                    via=[
                        {"snippet": 2, "label": "First"},
                        {"snippet": 1, "label": "Second"},
                        {"snippet": 3, "label": "Third"},
                    ]
                ),
            ),
            ("dangling via snippet ref", lambda path: path.update(via=[{"snippet": 4, "label": "Missing"}])),
            ("boolean via snippet ref", lambda path: path.update(via=[{"snippet": True, "label": "Invalid"}])),
            (
                "unknown via endpoint field",
                lambda path: path.update(via=[{"snippet": 2, "label": "Reconciliation", "extra": "not allowed"}]),
            ),
            (
                "repeated via source owner",
                lambda path: path.update(via=[{"snippet": 3, "label": "Same as destination"}]),
            ),
            ("missing via snippet ref", lambda path: path.update(via=[{"label": "Missing reference"}])),
            ("missing via label", lambda path: path.update(via=[{"snippet": 2}])),
            ("oversized via label", lambda path: path.update(via=[{"snippet": 2, "label": "x" * 121}])),
        )
        for phase in ("before", "after"):
            for label, mutate in cases:
                with self.subTest(phase=phase, case=label):
                    raw = with_paths(manifest())
                    path = raw["knots"][0]["comparison"][phase]["paths"][0]
                    mutate(path)
                    with self.assertRaises(renderer.InputError):
                        renderer.validate_manifest(raw)

        raw = with_paths(manifest())
        raw["knots"][0]["comparison"]["before"]["paths"][0]["via"] = [valid_node]
        renderer.validate_manifest(raw)

    # Behavior owner: when either phase supplies via, both routes have distinct source owners.
    def test_comparison_via_rejects_repeated_owners_in_the_other_phase(self):
        raw = with_paths(manifest())
        comparison_record = raw["knots"][0]["comparison"]
        comparison_record["before"]["paths"][0]["via"] = [
            {"snippet": 2, "label": "Reconciliation helper"}
        ]
        comparison_record["after"]["snippets"].append(
            {"path": "source/orders.py", "line": 5, "code": "orders_again"}
        )
        comparison_record["after"]["paths"][0]["to"] = {
            "snippet": 4,
            "label": "Orders again",
        }

        with self.assertRaises(renderer.InputError):
            renderer.validate_manifest(raw)

    def test_order_write_preview_shows_changed_data_between_the_same_files(self):
        data = renderer.validate_manifest(example_manifest())
        knot = next(record for record in data["knots"] if record["id"] == 1)
        phases = route_phases(ET.fromstring(renderer.render_path_comparison_svg(knot, "write-order")))

        for group in phases.values():
            wires = elements_by_class(group, "path", "route-wire")
            self.assertEqual(
                [(wire.get("data-from"), wire.get("data-to")) for wire in wires],
                [("src/orders.py", "src/storage.py")],
            )
        before_text = " ".join(phases["before"].itertext())
        after_text = " ".join(phases["after"].itertext())
        self.assertIn("JSON bytes", before_text)
        self.assertIn("Encode JSON", before_text)
        self.assertIn("Order record", after_text)
        self.assertIn("Encode and append", after_text)

    # Behavior owner: render_path_comparison_svg draws all supplied handoffs with shared owner positions.
    def test_path_comparison_renders_real_handoffs_owners_and_counts(self):
        data = renderer.validate_manifest(example_manifest())
        knot = next(record for record in data["knots"] if record["id"] == 2)
        svg = renderer.render_path_comparison_svg(knot, "price-lookup")
        root = ET.fromstring(svg)
        phases = route_phases(root)

        self.assertEqual(set(phases), {"before", "after"})
        expected_wires = {
            "before": {
                ("src/quotes.py", "src/orders.py"),
                ("src/orders.py", "src/storage.py"),
                ("src/storage.py", "src/catalog.py"),
            },
            "after": {("src/quotes.py", "src/catalog.py")},
        }
        owner_positions = {}
        for phase, group in phases.items():
            wires = elements_by_class(group, "path", "route-wire")
            actual_wires = {
                (wire.get("data-from", ""), wire.get("data-to", ""))
                for wire in wires
            }
            self.assertEqual(actual_wires, expected_wires[phase])
            self.assertEqual(
                {wire.get("stroke") for wire in wires},
                {"#f4a261"},
            )
            owners = elements_by_class(group, "g", "route-owner")
            self.assertEqual(len(owners), 4)
            owner_positions[phase] = {
                owner.get("data-file", ""): owner.get("transform", "")
                for owner in owners
            }
            self.assertEqual(
                set(owner_positions[phase]),
                {"src/quotes.py", "src/orders.py", "src/storage.py", "src/catalog.py"},
            )

        self.assertEqual(owner_positions["before"], owner_positions["after"])
        before_owners = {
            owner.get("data-file", ""): owner
            for owner in elements_by_class(phases["before"], "g", "route-owner")
        }
        after_owners = {
            owner.get("data-file", ""): owner
            for owner in elements_by_class(phases["after"], "g", "route-owner")
        }
        self.assertEqual(
            {path: owner.get("data-active") for path, owner in before_owners.items()},
            {path: "true" for path in before_owners},
        )
        self.assertEqual(
            {path: owner.get("data-active") for path, owner in after_owners.items()},
            {
                "src/quotes.py": "true",
                "src/orders.py": "false",
                "src/storage.py": "false",
                "src/catalog.py": "true",
            },
        )
        for path in ("src/orders.py", "src/storage.py"):
            with self.subTest(outside_owner=path):
                self.assertIn("outside this route", " ".join(after_owners[path].itertext()))

        self.assertIn("3 handoffs", " ".join(phases["before"].itertext()))
        self.assertIn("1 handoff", " ".join(phases["after"].itertext()))
        self.assertNotIn(
            ("src/quotes.py", "src/catalog.py"),
            expected_wires["before"],
        )
        for location in (
            "src/quotes.py:7",
            "src/orders.py:8",
            "src/storage.py:18",
            "src/catalog.py:4",
            "src/quotes.py:10",
        ):
            with self.subTest(location=location):
                self.assertIn(location, svg_text(svg))

    # Behavior owner: render_svg and render_html embed a comparison when either phase supplies via.
    def test_full_renderers_embed_route_comparison_for_via_in_either_phase(self):
        for via_phase in ("before", "after"):
            with self.subTest(via_phase=via_phase):
                data = renderer.validate_manifest(route_comparison_manifest(via_phase))
                svg = renderer.render_svg(data)
                page = renderer.render_html(data, svg)

                self.assertEqual(set(route_phases(ET.fromstring(svg))), {"before", "after"})
                for document in (svg, page):
                    self.assertIn('class="route-phase"', document)
                    self.assertIn('data-phase="before"', document)
                    self.assertIn('data-phase="after"', document)
                if via_phase == "after":
                    self.assertNotIn("DIRECT ROUTE · KNOT", svg)

    def test_checkout_storage_preview_shows_both_routes(self):
        manifest = renderer.validate_manifest(example_manifest())
        knot = next(record for record in manifest["knots"] if record["id"] == 1)
        svg = ET.fromstring(renderer.render_knot_routes_svg(knot, ("read-pending-orders", "write-order")))
        read, write = elements_by_class(svg, "svg", "path-comparison")
        self.assertGreater(float(write.get("y")), float(read.get("y")) + float(read.get("height")))
        self.assertIn("Read pending orders", " ".join(read.itertext()))
        self.assertIn("Write an order", " ".join(write.itertext()))
        self.assertIn("Order record", " ".join(write.itertext()))

    def test_complete_checkout_map_opens_with_the_direct_report_route(self):
        svg = ET.fromstring(renderer.render_svg(renderer.validate_manifest(example_manifest())))
        diagrams = [element for element in svg if element.tag == f"{{{SVG_NS}}}svg"]
        self.assertEqual([element.get("class") for element in diagrams], ["path-comparison", "comparison", "path-comparison"])
        focus, overview, price = diagrams
        self.assertGreater(float(overview.get("y")), float(focus.get("y")) + float(focus.get("height")))
        phases = route_phases(focus)
        before = elements_by_class(phases["before"], "path", "route-wire")
        after = elements_by_class(phases["after"], "path", "route-wire")
        self.assertEqual(
            [(wire.get("data-from"), wire.get("data-to")) for wire in before],
            [
                ("src/storage.py", "src/history.py"),
                ("src/history.py", "src/orders.py"),
                ("src/orders.py", "src/reconcile.py"),
            ],
        )
        self.assertEqual(sum(" C " in wire.get("d") for wire in before), 2)
        self.assertEqual([(wire.get("data-from"), wire.get("data-to")) for wire in after],
                         [("src/storage.py", "src/reconcile.py")])
        self.assertIn(" L ", after[0].get("d"))
        self.assertEqual(len(snapshot_panels(overview)), 2)
        self.assertIn("Look up a price", " ".join(price.itertext()))
        description = svg.findtext(f"{{{SVG_NS}}}desc")
        self.assertIn("Before: Return raw rows → History helper → Order helper → Decode and filter.", description)
        self.assertIn("After: Decode stored rows → Filter pending orders.", description)

    # Behavior owner: the standalone route SVG escapes untrusted path text.
    def test_route_comparison_escapes_text_in_standalone_and_embedded_outputs(self):
        raw = route_comparison_manifest()
        dangerous_label = '<script>alert("x & y")</script>'
        raw["knots"][0]["comparison"]["before"]["paths"][0]["via"][0]["label"] = dangerous_label
        data = renderer.validate_manifest(raw)
        knot = data["knots"][0]
        standalone = renderer.render_path_comparison_svg(knot, "price-lookup")
        full_svg = renderer.render_svg(data)
        page = renderer.render_html(data, full_svg)

        ET.fromstring(standalone)
        for document in (standalone, full_svg, page):
            with self.subTest(output_length=len(document)):
                self.assertIn("&lt;script&gt;", document)
                self.assertIn("&amp;", document)
                self.assertNotIn(dangerous_label, document)

    # Behavior owner: render_svg and render_html show paired data flow and source anchors.
    def test_paired_paths_render_labels_values_and_source_references(self):
        raw = with_paths(manifest())
        data = renderer.validate_manifest(raw)
        svg = renderer.render_svg(data)
        page = renderer.render_html(data, svg)
        text = svg_text(svg)

        for value in (
            "Persist order record 1",
            "Order object",
            "Stored record",
            "Serialized order JSON bytes",
            "source/orders.py:2",
            "source/storage.py:10",
            "source/orders.py:3",
            "source/storage.py:2",
            "Feature/file connections unchanged",
        ):
            with self.subTest(content=value):
                self.assertIn(value, text)
                self.assertIn(value, page)
        self.assertIn("→", page)
        self.assertIn("encoded = json.dumps(order)", page)
        self.assertIn("storage.write_order(order)", page)
        svg_paths = ET.fromstring(svg).findall(".//{http://www.w3.org/2000/svg}path")
        self.assertGreaterEqual(len(svg_paths), 4)

    # Behavior owner: renderers escape path labels as untrusted display text.
    def test_paired_path_labels_are_escaped_in_svg_and_html(self):
        raw = with_paths(manifest())
        raw["knots"][0]["comparison"]["before"]["paths"][0]["from"]["label"] = (
            '<img src=x onerror="alert(1)">'
        )
        raw["knots"][0]["comparison"]["after"]["paths"][0]["from"]["label"] = (
            '<img src=x onerror="alert(1)">'
        )
        data = renderer.validate_manifest(raw)
        svg = renderer.render_svg(data)
        page = renderer.render_html(data, svg)

        self.assertIn("&lt;img src=x onerror=", svg)
        self.assertIn("&lt;img src=x onerror=", page)
        self.assertIn("alert(1)", svg)
        self.assertIn("alert(1)", page)
        self.assertNotIn('<img src=x onerror="alert(1)">', page)
        ET.fromstring(svg)

    # Behavior owner: render_svg and render_html preserve the full wiring overview first.
    def test_full_wiring_overview_precedes_source_explanations(self):
        data = renderer.validate_manifest(with_paths(manifest()))
        svg = renderer.render_svg(data)
        page = renderer.render_html(data, svg)

        root = ET.fromstring(svg)
        nested_overview = next(
            element
            for element in root
            if element.tag == f"{{{SVG_NS}}}svg" and element.get("class") == "comparison"
        )
        child_text = [element.text or "" for element in root]
        explanation_index = child_text.index("WHAT WAS UNTIED")
        self.assertLess(list(root).index(nested_overview), explanation_index)
        self.assertEqual(len(snapshot_panels(nested_overview)), 2)

        figure_start = page.index("<figure")
        explanation_start = page.index('<section class="change-intro"')
        self.assertLess(figure_start, explanation_start)
        html_root = ET.fromstring(html_overview_svg(page))
        before, after = snapshot_panels(html_root)
        self.assertEqual(len(panel_routes(before)), 2)
        self.assertEqual(len(panel_routes(after)), 2)

    # Behavior owner: _render_panel shows only the true symmetric-difference routes.
    def test_full_wiring_routes_style_only_snapshot_specific_pairs_as_changed(self):
        raw = with_paths(manifest())
        raw["after"]["edges"][0]["file"] = "source/storage.py"
        raw["after"]["edges"][0]["evidence"][0]["path"] = "source/storage.py"
        data = renderer.validate_manifest(raw)
        svg = renderer.render_svg(data)
        page = renderer.render_html(data, svg)

        root = ET.fromstring(svg)
        before_panel, after_panel = snapshot_panels(root)
        before_routes = panel_routes(before_panel)
        after_routes = panel_routes(after_panel)
        expected_before = {("0", "source/orders.py"), ("0", "source/reconcile.py")}
        expected_after = {("0", "source/storage.py"), ("0", "source/reconcile.py")}
        self.assertEqual(set(before_routes), expected_before)
        self.assertEqual(set(after_routes), expected_after)

        before_changed = {pair for pair, edge in before_routes.items() if edge.get("stroke-dasharray")}
        after_changed = {pair for pair, edge in after_routes.items() if edge.get("stroke-dasharray")}
        self.assertEqual(before_changed, {("0", "source/orders.py")})
        self.assertEqual(after_changed, {("0", "source/storage.py")})
        for routes, changed_pair, stable_pair in (
            (before_routes, ("0", "source/orders.py"), ("0", "source/reconcile.py")),
            (after_routes, ("0", "source/storage.py"), ("0", "source/reconcile.py")),
        ):
            changed_width = float(routes[changed_pair].get("stroke-width", "0"))
            stable_width = float(routes[stable_pair].get("stroke-width", "0"))
            self.assertGreater(changed_width, stable_width)
            self.assertIsNone(routes[stable_pair].get("stroke-dasharray"))

        overview_text = " ".join(" ".join(text for text in root.itertext() if text).split())
        self.assertIn("1 retained, 1 added, 1 removed", overview_text)
        self.assertEqual(overview_text.count("2 feature/file pairs"), 2)
        self.assertIn("1 retained, 1 added, 1 removed", page)
        html_root = ET.fromstring(html_overview_svg(page))
        html_before, html_after = snapshot_panels(html_root)
        self.assertEqual(set(panel_routes(html_before)), expected_before)
        self.assertEqual(set(panel_routes(html_after)), expected_after)

    # Behavior owner: comparison rendering treats source excerpts as text.
    def test_comparison_escapes_markup_in_svg_and_html(self):
        raw = manifest()
        raw["knots"][0]["comparison"]["after"]["snippets"][0]["code"] = (
            "<img src=x onerror=alert(1)>"
        )
        data = renderer.validate_manifest(raw)

        svg = renderer.render_svg(data)
        page = renderer.render_html(data, svg)
        root = ET.fromstring(svg)

        self.assertFalse(any(element.tag.endswith("image") for element in root.iter()))
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", svg)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", page)
        self.assertNotIn("<img src=x onerror=alert(1)>", page)

    # Behavior owner: the HTML map preserves every explanation beyond the SVG cap.
    def test_html_keeps_all_comparisons_when_svg_shows_only_three(self):
        raw = manifest()
        raw["knots"] = []
        for index in range(1, 5):
            knot = copy.deepcopy(manifest()["knots"][0])
            knot["id"] = index
            knot["title"] = f"Knot {index}"
            knot["comparison"] = comparison(index)
            raw["knots"].append(knot)
        data = renderer.validate_manifest(raw)

        svg = renderer.render_svg(data)
        page = renderer.render_html(data, svg)
        text = svg_text(svg)

        self.assertIn("3 of 4", text)
        self.assertNotIn("Callers handle JSON conversion 4.", text)
        for index in range(1, 5):
            with self.subTest(knot=index):
                self.assertIn(f"Callers handle JSON conversion {index}.", page)
                self.assertIn(f"Storage owns JSON conversion {index}.", page)

    # Behavior owner: read-only maps continue to report that no after state ran.
    def test_read_only_manifest_does_not_invent_an_after_comparison(self):
        raw = manifest()
        raw["after"] = None
        raw["knots"][0].pop("comparison")
        data = renderer.validate_manifest(raw)

        svg = renderer.render_svg(data)
        page = renderer.render_html(data, svg)
        text = svg_text(svg)

        self.assertIn("AFTER NOT RUN", text)
        self.assertIn("after is null in the evidence manifest", page)
        self.assertNotIn("wiring unchanged", text.lower())


if __name__ == "__main__":
    unittest.main()
