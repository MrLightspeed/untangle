# Reuse repository-owned diagrams without importing their assumptions

Prefer an existing maintained generator when it can produce the required
feature/file evidence, ranked findings, and observed comparison views. Inspect
its schema, freshness checks, and graph semantics before adapting it. Generated
HTML should not become a second hand-maintained source of truth.

## Discover the target's diagram setup

Inspect the target repository's documentation and declared scripts for an
existing architecture or dependency map. Discover its actual paths, commands,
language tooling, and evidence model; do not assume a particular repository
layout, framework, task runner, or programming language.

A useful setup separates the evidence model from its presentation, generates an
offline HTML page, and checks model validity and output freshness. It can bind
feature roots, reachable files, findings, and historical snapshots to source
revisions. File search, feature filtering, selection highlighting, keyboard
operation, and comparison views make that evidence easier to inspect. Adapt the
target's setup only when it supports the requested evidence and views.

For a project without an equivalent generator, use this skill's portable
renderer. Build the map from evidence in the target project; do not copy another
project's findings or measurements.

## Keep the useful distinctions

1. Keep one versioned evidence model and generate the HTML and comparison from
   it. Validate endpoints and bind every historical location to its source
   state.
2. Label the graph accurately. A feature-to-file transitive closure is not a
   file-import graph; a file-import graph is not an execution/call graph. Label
   counts by what they actually count.
3. Use explicit group counts for large maps and retain exact searchable file
   memberships and evidence. A grouping edge can summarize several real edges;
   its displayed count must make that clear.
4. Separate visual selection/filtering from the underlying evidence. Hidden by a
   filter does not mean deleted, unused, or fixed. Preserve unfiltered totals.
5. Bind before/current views to actual source snapshots. A historical finding's
   old line number or old validation result is not proof about current HEAD.
   Show matched excerpts and explain what moved, why it helps, and what the
   checks preserve. Wiring can stay identical when responsibility changes.
6. Keep a legend and explanatory text adjacent to the image. Include omitted
   dynamic paths, relevant external boundaries, and validation limits.

Static import or dependency inventories provide discovery evidence, but may miss
dynamic loading, configuration, generated registration, and cross-language
boundaries. They cannot by themselves establish when code executes or prove all
runtime feature paths. Augment them with actual caller, registration, and
state-ownership inspection appropriate to the target's languages and tooling.

Allow shared files to belong to multiple features. Preserve useful existing
architecture diagrams rather than replacing them solely to standardize their
appearance.
