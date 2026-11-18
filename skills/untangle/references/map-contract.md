# Wiring-map evidence contract

The renderer visualizes a supplied evidence manifest. It does not discover
features, prove reachability, find defects, run tests, or modify repository
code. The agent must trace and substantiate its data before rendering it.

## Invocation and files

```text
python <skill-directory>/scripts/render_map.py <run-directory>/evidence.json --output-dir <run-directory>/map-before
```

Use a fresh output directory for the final render, preserving the initial map.
The renderer emits `untangle.html`, `comparison.svg`, and `map.json`. When knots
include source comparisons, the SVG explains those changes; the HTML retains
every explanation and the feature/file wiring as context. Without comparisons,
the SVG remains a wiring overview. It refuses to replace existing outputs unless
`--overwrite` is explicitly supplied. Verify the exact directory and those
task-owned files before using that option. It requires Python 3.13 or newer with
its standard library, no installs or network. Hard-link support is optional;
filesystems without it use exclusive file copies. Before publication completes,
a handled error or cancellation attempts to restore previous outputs without
replacing a concurrent target. If filesystem errors prevent restoration, the
renderer preserves and reports exact retained recovery-copy paths; rollback
cannot be guaranteed through arbitrary filesystem failures. Once all
replacements are published, interruption of backup cleanup preserves the
complete new set. Abrupt process termination or power loss cannot run cleanup;
preserve any named backup files for recovery.

Each portable view accepts up to 18 feature rows, 2,000 files, 4,000 edges per
snapshot, and a 2 MB input manifest. These are rendering limits, not permission
to reduce the requested scope. For a larger task, retain a repository-wide
overview/index with linked subsystem views covering the complete inventory, or
use an existing repository generator that supports that scale. State all view
boundaries and outstanding coverage. Never truncate a manifest to make the
renderer accept it.

### Validation, preview, and machine output

Replace `<skill-directory>` with your installed Untangle directory and
`<run-directory>` with the location of the agent's evidence manifest:

```text
python <skill-directory>/scripts/render_map.py <run-directory>/evidence.json --check --json
python <skill-directory>/scripts/render_map.py <run-directory>/evidence.json --output-dir <run-directory>/map-preview --dry-run --json
python <skill-directory>/scripts/render_map.py --schema
```

`--check` (also `--validate-only`) validates the input without rendering or
inspecting output targets. `--dry-run` also renders in memory and checks output
safety, then lists the three planned output paths. It creates no directories or
files. Preview existing task-owned outputs with `--dry-run --overwrite` before
replacing them with a separate `--overwrite` invocation. A preview is a check of
current state; a later render checks safety again.

`--json` writes one object to stdout. Its envelope has integer
`schema_version: 1`, `ok`, and `mode`. Successful modes are `check`, `dry-run`,
and `render`, with a `result` object. Rendering and preview results list output
paths and actions. Failures use `mode: "error"` and an `error` object with
`code`, `message`, `context`, and `hint`. Diagnostics also go to stderr. Error
codes distinguish `input_error`, `argument_error`, `safety_error`,
`filesystem_error`, and `cancelled`. `--schema` exports the JSON Schema for
these CLI results without reading input; it describes the result envelope, not
the input manifest. The input contract below remains authoritative.

Exit status is `0` for success, help, or schema output and `2` for handled
input, argument, safety, or filesystem errors. Handled cancellation returns
`130`, with `error.code: "cancelled"` in JSON mode and a diagnostic on stderr.
Cancellation during publication runs the same recovery path described above.
Inspect the output directory and any reported recovery copies before retrying;
an interruption after publication may leave the complete new set in place.
Repeated interruption, forced termination, and power loss cannot guarantee
cleanup. Use `error.code` for finer distinctions. `--help` always prints text,
even with `--json`. The renderer emits no colors, prompts, or progress timers
and works with redirected streams. Output ordering and artifact bytes are stable
for the same validated evidence.

The SVG is already a single comparison image. For a PNG, open it using a
supported browser, capture the rendered SVG, and inspect the capture. Preserve
both formats when useful. If PNG capture is unavailable, provide the SVG and
state that limitation; do not report an uncaptured PNG as delivered.

## Schema, version 1

```json
{
  "schema_version": 1,
  "title": "Untangle / Example service",
  "scope": "Orders subsystem; first-party runtime, configuration and contract tests",
  "features": [{ "id": "orders", "label": "Place order" }],
  "knots": [
    {
      "id": 1,
      "category": "drifted-duplication",
      "severity": "high",
      "title": "Repeated order policy",
      "features": ["orders"],
      "locations": [{ "path": "src/orders.py", "line": 42 }],
      "evidence": "Explain the confirmed shared rule and caller impact here.",
      "remedy": "Move the shared rule to its domain owner and update both callers.",
      "status": "open",
      "verification": []
    }
  ],
  "before": {
    "revision": "<full baseline commit plus dirty-input identity if applicable>",
    "coverage": "Entry points and configured consumers traced; list unresolved paths/exclusions.",
    "files": ["src/orders.py"],
    "edges": [
      {
        "feature": "orders",
        "file": "src/orders.py",
        "evidence": [
          {
            "path": "src/orders.py",
            "line": 42,
            "note": "Actual call path or registration proving this feature touches the file.",
            "kind": "direct"
          }
        ]
      }
    ]
  },
  "after": null
}
```

This illustrates shape, not a real finding or reusable source evidence. Replace
every example value with inspected facts; do not copy claims into a live map.

- `features`: stable unique IDs, labels, and order used by both panels.
  Represent a retired feature explicitly in the evidence rather than quietly
  removing it.
- Snapshot `revision` and `coverage`: identify the exact observed source state
  and trace limits. Record a reproducible patch or content identity for a dirty
  state; the label alone is insufficient.
- Snapshot `files`: exact unique repository-relative POSIX paths. No absolute
  paths, backslashes, empty segments, or `..`. Include files relevant to the
  declared scope. Exclude vendor/build artifacts and secret material explicitly.
- Snapshot `edges`: one entry per feature/file pair; every edge must have at
  least one exact source location and explanation. `kind` is `direct`,
  `transitive`, `configured`, or `observed`. A transitive edge explains the call
  chain; a configured edge identifies registration; an observed edge describes
  the bounded runtime evidence. Mark unresolved dynamic paths in coverage, not
  as proven edges. Source evidence can cite a different caller file. In
  `coverage`, say which runtime, initialization, configuration, and test
  relationships count toward the map. Apply the same rule to both snapshots.
  Label initialization and test-only links in their evidence notes. A file can
  leave an operation's call route and still appear in its test setup or shared
  initialization. Use the paired paths to explain the specific handoffs that
  changed.
- Knot `category`: `leaky-abstraction`, `drifted-duplication`,
  `stale-workaround`, `empty-wrapper`, `dependency-cycle`, or
  `mixed-responsibilities`. `severity`: `high`, `medium`, or `low`. IDs are
  stable positive integers and locations use positive one-based lines at the
  baseline.
- Knot `status`: `open`, `fixed`, `rolled-back`, `blocked`, or `deferred`.
  Evidence includes the consequence, confidence, and prerequisites. Record the
  rollback result/failure reason in verification notes when applicable.
- Knot `verification`: entries have `kind` (`tests`, `build`, or `other`),
  `command`, `result` (`pass`, `fail`, `blocked`, or `not-applicable`), and
  optional `note`. Use the latest disposition for each selected command; retain
  failed attempt details in the checkpoint record. A fixed knot requires a
  passing build/equivalent and passing tests, or explicitly documented absence
  of tests. It also requires a real `after` snapshot. Test logs and the
  structural inspection remain the agent's proof obligations beyond schema
  validation.

Use `dependency-cycle` only for a confirmed directed loop of module imports or
calls. Record the actual module path or call chain with source locations, and
explain its material effect on changes, tests, or startup. Feature-to-file wires
show which files a feature touches. They do not encode module-to-module
direction and cannot establish a dependency cycle.

Use `mixed-responsibilities` for either a module with unrelated reasons to
change or one coherent change scattered across several owners. State which case
applies. For the first, identify the unrelated responsibilities and affected
callers. For the second, trace the shared rule or change path and the
coordinated edits it requires. Scattering alone does not prove any individual
module has mixed responsibilities; file count and intentional orchestration are
insufficient evidence for either case.

## Explain what changed

Use the full before/after feature/file wiring overview to show the scope. The
static SVG can lead with a fixed route that drops intermediate owners between
the same endpoint files. The interactive HTML starts with the wiring overview.
Keep stable feature colors and file positions, mark affected files with numbered
knots, and distinguish routes present in only one snapshot. Dashed routes in the
supplied renderer contain connections present in that snapshot only. A grouped
route may also contain retained connections; its count and the exact inventory
show the full membership. Keep unchanged routes visible so the reader can judge
the scope of the change.

Follow the wiring overview with the explanation for each numbered knot. Link
each close-up path or code excerpt to the knot it explains.

For each changed knot, add a `comparison` object alongside its existing fields.
Record the observed responsibility change and source excerpts from both
snapshots. Explain why it helps and what the checks preserve. Do not use a
cleaner layout or a different badge color as the explanation.

| Field       | Content                                                                                  |
| ----------- | ---------------------------------------------------------------------------------------- |
| `before`    | Object with a `summary`, `snippets`, and optional `paths` from the baseline.             |
| `after`     | Object with a `summary`, `snippets`, and optional `paths` from the observed final state. |
| `benefit`   | Why the actual change addresses the knot; state any remaining limits.                    |
| `preserved` | Observable behavior covered by the recorded checks, with its scope.                      |

Each phase needs one to six snippets. A snippet contains only `path`, `line`,
and `code`: the snapshot-relative file path, its first one-based line number,
and a verbatim contiguous excerpt, including indentation. Paths must occur in
that phase's `files` inventory. Each excerpt may contain up to 1,000 characters
and 12 lines; each summary is limited to 400 characters, and `benefit` and
`preserved` to 700 characters each. Choose short excerpts that show the caller
and the new owner, rather than copying entire modules.

The renderer validates this shape and membership in the declared snapshot.
Before rendering, compare each excerpt with the designated source revision at
its recorded path and first line. Check every handoff against the call or data
transfer it describes. Capture the exact commands and outcomes at the verified
revision before recording a passing check. The repository's
[worked example](https://github.com/MrLightspeed/untangle/blob/main/examples/README.md)
checks its excerpts against both bundled snapshots.

### Show the paths across a boundary

Add `paths` to both phases to show the data passed between source owners. Each
phase accepts one to four records with these exact fields:

| Field   | Content                                                             |
| ------- | ------------------------------------------------------------------- |
| `id`    | Stable path identifier, up to 80 characters.                        |
| `label` | Operation being compared, up to 120 characters.                     |
| `from`  | Object with `snippet` and `label` for the sender.                   |
| `via`   | Optional array of one or two intermediate owners, in handoff order. |
| `to`    | Object with `snippet` and `label` for the receiver.                 |
| `value` | Data crossing the boundary, up to 100 characters.                   |

An endpoint's `snippet` is a positive, one-based index into its own phase's
`snippets` array. Its `label` describes the operation in up to 120 characters.
Before and after must use the same path IDs, labels, and order. Endpoint labels
and transferred values can change to describe the observed refactor.

For a route through several owners, supply `via` endpoints with the same
`snippet` and `label` fields. Every owner in that route must have a distinct
source file. The renderer draws each handoff in order, keeps the owners in
stable positions across snapshots, and marks owners outside a phase's route. The
transferred `value` must describe the data passed along the whole route; use
separate paths when a handoff changes its representation. Omit `via` when the
sender reaches the receiver directly. Existing two-endpoint paths remain valid.

The price example records the complete route through quotes, orders, storage,
and catalog before the change, and the direct quotes-to-catalog route after it.
The three-to-one handoff count comes from those endpoints. Curved crossings show
the supplied routes; they do not add a dependency or prove a defect.

Arrows show data flow, including returned values. They are not module dependency
edges or a complete execution trace. Trace each handoff and check its source
references before recording it. The example compares raw JSON bytes crossing the
storage boundary with records crossing that boundary after conversion moves
inside storage. This JSON ownership change retains its operations and
feature/file connections.

With paired paths, the SVG prioritizes the wiring diagrams, source locations,
benefit, and preserved behavior. Exact code excerpts remain expandable and
searchable in the HTML beside the diagrams. Comparisons without paths still
render the source excerpts in the SVG.

This field is optional for existing version 1 manifests. A supplied comparison
requires a real `after` snapshot; omit it in a read-only audit with
`after: null`. The SVG shows up to three comparisons in severity and ID order
and discloses the count. The HTML retains all comparisons, full excerpts, source
references, and verification records. The SVG removes common leading indentation
and may wrap long code lines; the HTML keeps their original formatting.
Feature/file pair changes are counted separately: an ownership correction can
leave every connection intact.

## Visual truth and scaling

Feature wire colors are categorical and remain stable between snapshots. The
close-up data-flow arrows use the same neutral color before and after. Green
belongs to the supplied fixed-knot status, not to a claim that a wire is
correct. Fixed status requires an observed after snapshot, a passing build, and
passing tests or the documented absence of tests described above. The renderer
checks those records but does not execute the commands or prove that the
structural cause was removed. Keep the source explanation and actual check
results beside the status.

Use consistent feature colors independently of severity. Red numbered badges
mean unresolved knots; a resolved badge must remain identifiable. Before and
after come from the same evidence schema and comparable scope. Keep every
remaining actual edge, even if it makes the final picture less tidy.

The one-screen overview may group directories for legibility. Labels must state
grouping and counts, and the HTML must retain searchable exact files, edges, and
evidence. If the overview still cannot be read, split detail views by subsystem
and disclose the coverage; do not silently drop edges. Read-only runs leave
`after` null and clearly label the right panel not performed. Full runs use the
actual final state, even when it equals the baseline.

Do not claim complete repo coverage until the feature inventory and all relevant
paths have been inspected. Show declared exclusions, unresolved dynamic paths,
and source-state identities in the HTML. Metrics count evidence records, not
unverified imports, and reduced wire count is not proof of improvement.
