# Untangle

[![License: MIT](assets/badges/license.svg)](LICENSE)
[![Python: 3.13 or newer](assets/badges/python.svg)](INSTALL.md)
[![CI: Bun only](assets/badges/ci.svg)](https://github.com/MrLightspeed/untangle/actions/workflows/check.yml)
[![Latest GitHub release](https://img.shields.io/github/v/release/MrLightspeed/untangle?style=for-the-badge&labelColor=0b1220&color=c4b5fd)](https://github.com/MrLightspeed/untangle/releases)
[![GitHub stars](https://img.shields.io/github/stars/MrLightspeed/untangle?style=for-the-badge&labelColor=0b1220&color=f5be78)](https://github.com/MrLightspeed/untangle/stargazers)
[![Sponsor Untangle](assets/badges/sponsor.svg)](https://github.com/sponsors/MrLightspeed)

Untangle helps coding agents untangle spaghetti code while preserving the
program's behavior. It maps the files behind a feature and records each accepted
knot with source evidence, its concrete impact, and a proposed correction.

![Untangle output for the checkout example. Before, quote reaches the catalog
through orders and storage. After, quote calls the catalog directly. Three
handoffs become one.](assets/example-price-route.svg)

As an example, `quotes.py` used to pass the product ID through `orders.py` and
`storage.py` to reach `catalog.py`. After the refactor, `quotes.py` calls the
catalog directly. The two files still serve other features.
[Open price route](assets/example-price-route.svg) ·
[Before source](examples/checkout/before/src/quotes.py#L7) ·
[After source](examples/checkout/after/src/quotes.py#L10)

Start with a read-only audit to map a codebase and rank its knots. For an
authorized refactor, the agent works through the knots on a local branch, saves
a recoverable checkpoint, and runs the relevant tests and build after each
change. The final map compares the observed before and after states.

## Install

Run this in the project you want to untangle.

```sh
npx skills@latest add MrLightspeed/untangle --skill untangle --copy
```

Choose your agent if prompted. Untangle uses Git and renders maps with Python
3.13 or newer using the standard library. See the
[installation guide](INSTALL.md) for Bun, agent-specific commands, manual setup,
and fixed versions.

## Try Untangle

Open your agent in that project and ask for a map and recommendations.

```text
Use Untangle to map this repository in read-only mode.
```

Ask the agent to untangle the repository you are working in:

```text
Use $untangle to map and untangle this repository. Rank the knots by their
impact, preserve behavior, and verify each fix with the project's tests and
build, or documented equivalents. Save a recoverable checkpoint before each
change. Show the actual before/after wiring and explain which paths and
responsibilities changed. Keep all work on a local branch.
```

## Patterns Untangle addresses

Every accepted knot needs source locations, an observed consequence, a proposed
correction, and checks that can distinguish preserved behavior from a
regression. The table covers all six knot categories and the diagnostic clues,
techniques, and working method described in the skill's refactoring reference.

| Pattern                                  | Role                     | What to investigate or apply                                                                                                                                                              | Supporting source                                                                                                                                                                                                                                                  |
| ---------------------------------------- | ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Harmful dependency cycles                | Knot category            | A directed module dependency loop prevents useful independent testing, initialization, or change. Confirm the actual chain and consequence; a cycle alone is insufficient.                | Fowler, [Reducing Coupling](https://www.martinfowler.com/ieeeSoftware/coupling.pdf).                                                                                                                                                                               |
| Mixed or scattered responsibilities      | Knot category            | Distinguish one module changing for unrelated reasons from one coherent change requiring edits across several owners. Preserve intentional orchestration.                                 | Fowler and Beck, [Divergent Change](https://www.informit.com/articles/article.aspx?p=2952392&seqNum=7) and [Shotgun Surgery](https://www.informit.com/articles/article.aspx?p=2952392&seqNum=8).                                                                   |
| Leaky abstractions                       | Knot category            | Callers depend on another owner's representation, state or policy. Move that knowledge behind its actual contract while preserving observable behavior.                                   | Parnas, [module decomposition criteria](https://www.cs.lafayette.edu/~gexia/cs301/resources/parnas.html), and Fowler, [Module Dependencies](https://martinfowler.com/articles/refactoring-dependencies.html).                                                      |
| Drifted duplication                      | Knot category            | Copies of one domain rule disagree or require manual synchronization. Confirm shared meaning before consolidating; similar syntax alone is insufficient.                                  | Google Testing Blog, [Do not DRY prematurely](https://testing.googleblog.com/2024/05/dont-dry-your-code-prematurely.html).                                                                                                                                         |
| Stale workarounds                        | Knot category            | Verify the original compatibility condition no longer applies before removing a fallback. Age or absence from a static search does not prove obsolescence.                                | [Untangle evidence rules](skills/untangle/references/refactoring-practice.md) and Fowler, [Remove Dead Code](https://refactoring.com/catalog/removeDeadCode.html).                                                                                                 |
| Empty wrappers                           | Knot category            | Remove indirection only after checking APIs, test seams, extension points, permissions, retry policy, resource ownership and telemetry. A short function can still own a useful contract. | [Untangle evidence rules](skills/untangle/references/refactoring-practice.md) and Fowler, [Inline Function](https://refactoring.com/catalog/inlineFunction.html).                                                                                                  |
| Hidden state and call-order requirements | Diagnostic clue          | Identify undocumented initialization, shared mutable state and required sequences. Make ownership and lifecycle explicit; verify order, repeated use, failure and cleanup.                | Seemann, [Temporal Coupling](https://blog.ploeh.dk/2011/05/24/DesignSmellTemporalCoupling/), and Parnas, [module decomposition criteria](https://www.cs.lafayette.edu/~gexia/cs301/resources/parnas.html).                                                         |
| Tangled branches and mode flags          | Diagnostic clue          | Repeated switches obscure distinct operations or business decisions. Consider named operations, decomposed conditions or guard clauses while preserving evaluation and effect order.      | Fowler, [Flag Argument](https://martinfowler.com/bliki/FlagArgument.html) and [Guard Clauses](https://refactoring.com/catalog/replaceNestedConditionalWithGuardClauses.html).                                                                                      |
| Business decisions mixed with I/O        | Diagnostic clue          | A rule is difficult to test without a UI, database, filesystem or network boundary. Separate testable decisions from the code that performs effects when there is a demonstrated benefit. | Feathers, [The Humble Dialog Box](https://martinfowler.com/articles/images/humble-dialog-box/TheHumbleDialogBox.pdf), and Bernhardt, [Functional Core, Imperative Shell](https://www.destroyallsoftware.com/screencasts/catalog/functional-core-imperative-shell). |
| Split Phase                              | Refactoring technique    | Separate stages with a clear intermediate value so each stage can be understood and tested independently.                                                                                 | Fowler, [Split Phase](https://refactoring.com/catalog/splitPhase.html).                                                                                                                                                                                            |
| Maintenance hotspots                     | Prioritization technique | Use relevant change frequency and repeated changes across files to choose investigation targets. History supplements consequence and reach; it does not prove a defect.                   | Tornhill, [prioritizing technical debt](https://codescene.com/blog/prioritize-technical-debt-by-impact/).                                                                                                                                                          |
| Parallel Change                          | Migration technique      | For an authorized contract migration, support both interfaces, migrate all supported consumers, then remove the old path after verification.                                              | Sato, [Parallel Change](https://martinfowler.com/bliki/ParallelChange.html).                                                                                                                                                                                       |
| Branch by Abstraction                    | Migration technique      | Replace a supplier behind a small interface in verified steps, then retire the temporary adapter after its consumers have moved.                                                          | Fowler, [Branch by Abstraction](https://martinfowler.com/bliki/BranchByAbstraction.html).                                                                                                                                                                          |
| Test seams                               | Verification technique   | Introduce the smallest boundary needed to redirect an external effect or observe behavior. Preserve the normal execution owner.                                                           | Fowler, [Legacy Seam](https://martinfowler.com/bliki/LegacySeam.html).                                                                                                                                                                                             |
| Characterization tests                   | Verification technique   | Record what the affected code actually does, including errors and side effects. Investigate surprising behavior before endorsing it as the intended contract.                             | Feathers, [Characterization Testing](https://michaelfeathers.silvrback.com/characterization-testing).                                                                                                                                                              |
| Incremental refactoring                  | Working method           | Make one cohesive structural change, verify it and preserve a rollback point before continuing. Keep deliberate feature or behavior changes separately scoped.                            | Fowler, [Refactoring](https://www.martinfowler.com/books/refactoring.html), and Google, [Small CLs](https://github.com/google/eng-practices/blob/master/review/developer/small-cls.md).                                                                            |

The six category names and their proof requirements are Untangle's synthesis.
Diagnostic clues do not create extra category IDs, and a technique is not itself
a finding. The sources explain the underlying practices; they do not prescribe
Untangle's map format or Git workflow. See
[refactoring decisions](skills/untangle/references/refactoring-practice.md) for
corrections, proof, and reasons to leave code alone.

Public API or persistent-data changes need their own authority and proof. The
rendered map shows which files each feature touches; a dependency-cycle finding
needs an actual directed import or call chain. Crossed feature wires and a
simpler diagram cannot establish a defect or preserved behavior.

## What you get

| Artifact         | Purpose                                                                                            |
| ---------------- | -------------------------------------------------------------------------------------------------- |
| `untangle.html`  | Full interactive wiring map, numbered knots, and matched source explanations.                      |
| `comparison.svg` | A source route that became direct, when present, plus full before/after wiring and numbered knots. |
| `map.json`       | Validated source locations, coverage limits, knots, and verification notes used by the renderer.   |
| `comparison.png` | Optional browser capture of the SVG comparison.                                                    |

The renderer checks the manifest's structure and references. It does not inspect
a repository or prove the agent's findings. Coverage limits and unresolved paths
stay visible in the map.

### Before and after

![Two before-and-after routes from the checkout source. Pending orders used to
pass from storage through history and orders as JSON bytes. After the refactor,
storage sends decoded records directly to reconciliation. Order writing still
connects the same two files, with storage taking over encoding.](assets/untangle-banner.svg)

Before, the pending-order report received raw rows from storage through two
helpers, then decoded the JSON itself. Order creation encoded the same format on
the write side. After the refactor, the report calls `storage.read_orders()`
directly and order creation calls `storage.write_order(order)`. Storage now
handles both conversions. The report drops two handoffs, and the write path
carries an order record instead of bytes.
[Open both routes](assets/untangle-banner.svg) ·
[Before report](examples/checkout/before/src/reconcile.py) ·
[After report](examples/checkout/after/src/reconcile.py#L3) ·
[After storage](examples/checkout/after/src/storage.py#L18)

Untangle renders these routes from evidence checked against the bundled
snapshots. The full comparison follows the price, order, and report paths and
shows the recorded checks. Four feature/file connections disappear across the
two detours. The shared tests still check the same stored bytes and order
results. [Full comparison](assets/example-comparison.svg) ·
[Price route PNG](assets/untangle-before-after.png)

Shared tests check callable outputs, stored bytes and key order, validation
errors, operation order, pending-order filtering, and reads in both snapshots.
These results apply to the bundled `InMemoryStorage` fixture; they do not
establish behavior for other storage implementations.

The runnable [checkout example](examples/README.md) includes the source
snapshots, shared tests, and renderer evidence. From a checkout of this
repository, generate its map with:

```sh
python skills/untangle/scripts/render_map.py examples/evidence.json --output-dir work/example
```

Validate evidence or preview the output paths without writing files:

```sh
python skills/untangle/scripts/render_map.py examples/evidence.json --check --json
python skills/untangle/scripts/render_map.py examples/evidence.json --output-dir work/example-preview --dry-run --json
```

Use `--help` for examples and exit codes, or `--schema` for the machine-readable
result contract. See the
[map contract](skills/untangle/references/map-contract.md) for overwrite
safeguards and error categories.

## Compatibility

The workflow can be used with TypeScript, Python, and other languages your agent
can inspect and your project can verify. The renderer reads an evidence
manifest; it does not parse source code or refactor files itself.

Package and renderer checks run on Windows and Linux in
[CI](.github/workflows/check.yml). Local Skills CLI installation checks covered
Codex, Claude Code, Cursor, and GitHub Copilot. Codex completed a read-only
audit, and a separate agent verified a refactor and rollback on a scoped Python
project. Copilot produced an audit manifest. See
[installation and compatibility](INSTALL.md#compatibility) for the scope of
these checks.

## Contribute

Use issues for bug reports, help, and focused proposals. Start with an
[issue](https://github.com/MrLightspeed/untangle/issues/new/choose) before
opening a pull request. Share a fork or commit link there if you already have a
patch. The maintainer invites pull requests for agreed changes and may import a
patch with attribution. See [contributing](CONTRIBUTING.md) for the review
process.

For installation and usage questions, use [support](SUPPORT.md). Report
vulnerabilities through the [security policy](SECURITY.md). Follow the
[code of conduct](CODE_OF_CONDUCT.md).

## Support the project

[Sponsor Untangle on GitHub](https://github.com/sponsors/MrLightspeed). The page
offers one-time and monthly contributions.

## Develop

To change this repository, use the tool versions declared in
[package.json](package.json) and install from the committed lockfile:

```sh
bun install --frozen-lockfile --ignore-scripts
bun run check
```

npm contributors can use:

```sh
npm ci --ignore-scripts
npm run check
```

Both workflows use the same project-local Bun binary for formatting and
JavaScript linting. CI uses Bun only. See [contributing](CONTRIBUTING.md) for
formatting, tests, and the review process, and the [writing standard](STYLE.md)
for documentation conventions. These tools are not part of the installed skill.

## License

Untangle is available under the [MIT License](LICENSE). The installable skill
includes its own copy of the license.
