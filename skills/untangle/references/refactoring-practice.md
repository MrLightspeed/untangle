# Refactoring decisions and primary sources

Sources opened and checked on 2026-11-15 and 2026-11-16. These are documented
engineering practices; the Untangle workflow below is a synthesis, not a
universal standard or a proof of equivalence for any particular repository.

| Practice                                                                                                            | Application in Untangle                                                                                                                                                    | Primary source                                                                                                                                                                                                                             |
| ------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Refactoring changes structure while preserving observable behavior; small transformations reduce risk.              | Keep each knot independently reviewable and runnable. Establish the old behavior before rearranging it.                                                                    | Martin Fowler, [Refactoring, second edition](https://www.martinfowler.com/books/refactoring.html), 2018.                                                                                                                                   |
| Characterization tests expose what legacy code actually does. Surprising behavior needs investigation.              | Capture concrete happy, error, boundary, and lifecycle cases relevant to the change. Do not turn an unexplained bug into a newly endorsed specification.                   | Michael Feathers, [Characterization Testing](https://michaelfeathers.silvrback.com/characterization-testing), 2016-08-08.                                                                                                                  |
| Conceptually small review changes are easier to understand; separate substantial refactoring from feature work.     | One cohesive knot per checkpoint. Keep deliberate behavior changes separate.                                                                                               | Google Engineering Practices, [Small CLs](https://github.com/google/eng-practices/blob/master/review/developer/small-cls.md). The repository was archived in 2025; treat it as published practice, not a maintained runtime specification. |
| Similar-looking code need not represent the same abstraction. Premature deduplication couples independent concepts. | Confirm shared semantics and reasons to change before extracting a common owner. A small amount of duplication can be cheaper than the wrong abstraction.                  | Google Testing Blog, [Don't DRY Your Code Prematurely](https://testing.googleblog.com/2024/05/dont-dry-your-code-prematurely.html), 2024-05-28.                                                                                            |
| A seam permits behavior redirection without editing every dependency at the point of use.                           | Introduce the smallest test seam when external effects prevent characterization; avoid a general dependency framework for one test.                                        | Martin Fowler, [Legacy Seam](https://martinfowler.com/bliki/LegacySeam.html), 2024-01-04.                                                                                                                                                  |
| Branch by Abstraction supports incremental replacement behind an interface.                                         | For larger owner/boundary replacements, migrate callers in green steps, then remove the temporary adapter once it has no consumers. Use this only when warranted by scope. | Martin Fowler, [Branch By Abstraction](https://martinfowler.com/bliki/BranchByAbstraction.html), 2014-01-07.                                                                                                                               |

## Choose a correction by the actual knot

- **Dependency cycle:** trace a directed chain of imports or calls and show
  where the cycle prevents a useful change, test, build, or initialization
  sequence. Move the misplaced responsibility, split a module, or define a small
  contract at its actual owner. Check consumers, startup, and the affected
  features after each step. Leave a localized cycle alone when it has no
  demonstrated cost; the feature-to-file map does not prove module dependencies.
  See Parnas's
  [loop-free uses hierarchy](https://pages.mtu.edu/~aebnenas/teaching/spring2010/cs3141/readings/Parnas-Design4Change.pdf)
  and Fowler's
  [coupling discussion](https://www.martinfowler.com/ieeeSoftware/coupling.pdf).
- **Mixed responsibilities:** distinguish a module edited for unrelated reasons
  from one coherent change scattered across several modules. Show a real or
  well-supported change path, then move the related functions and data toward
  the owner that changes with them. Check each affected feature, API, and
  configuration path. Leave intentional orchestration and separate domain
  concepts alone. Fowler and Beck call the two smells
  [Divergent Change](https://www.informit.com/articles/article.aspx?p=2952392&seqNum=7)
  and
  [Shotgun Surgery](https://www.informit.com/articles/article.aspx?p=2952392&seqNum=8).
- **Leaky abstraction:** identify the policy/state owner and caller-visible
  contract. Move representation knowledge behind that contract. Check errors,
  cancellation, concurrency, ordering, transactions, and cleanup if affected. A
  new wrapper is useful only if it owns a real boundary or policy.
- **Drifted duplication:** enumerate the rules and all meaningful differences
  first. Consolidate only the common domain concept. Preserve explicit variants
  instead of adding boolean flags that encode unrelated use cases.
- **Stale workaround:** identify the original compatibility condition and verify
  supported environments no longer need it. Search configuration, release
  support, dynamic consumers, and fallback tests before removal. Unknown means
  defer; age alone does not establish obsolescence.
- **Empty wrapper:** verify it supplies no contract, resource boundary, retry,
  permission check, telemetry, extension point, test seam, or external API.
  Update every supported consumer when inlining it. Line count is irrelevant.

## Follow concrete clues within those categories

- **Hidden state or call order:** identify the required sequence, the owner of
  mutable state, and callers that rely on an undocumented lifecycle. Make the
  invariant explicit in the smallest suitable API or owner, where existing
  contracts permit it. Verify valid and invalid order, repeated use, failure,
  and cleanup. Leave an intentional documented protocol alone when callers can
  use it safely. Record this under leaky abstraction. See Seemann's
  [Temporal Coupling](https://blog.ploeh.dk/2011/05/24/DesignSmellTemporalCoupling/)
  for call order and Parnas's
  [module decomposition criteria](https://www.cs.lafayette.edu/~gexia/cs301/resources/parnas.html)
  for keeping data representations and their access procedures together.
- **Tangled decisions and mode flags:** look for repeated branches in which a
  flag selects different operations or nested conditions hide the main path.
  Consider named operations, decomposed conditions, or guard clauses; a private
  shared implementation may still need a flag. Verify each mode, evaluation
  order, side effects, errors, and cleanup. Leave a flag alone when it merely
  passes a value through or conveys a genuine domain choice. See Fowler's
  [Flag Argument](https://martinfowler.com/bliki/FlagArgument.html) and
  [Guard Clauses](https://refactoring.com/catalog/replaceNestedConditionalWithGuardClauses.html).
- **Decisions mixed with effects:** when business rules are buried in UI or I/O
  code, trace the input, decision, and external effect separately. Move the
  decision into a testable unit only when that reduces a proven maintenance or
  testing problem; keep the boundary responsible for performing effects. Test
  decisions and verify the actual effect order and error behavior at the
  boundary. Leave a small cohesive handler alone when extraction adds no clear
  owner. See Feathers's
  [Humble Dialog Box](https://martinfowler.com/articles/images/humble-dialog-box/TheHumbleDialogBox.pdf)
  and Bernhardt's
  [Functional Core, Imperative Shell](https://www.destroyallsoftware.com/screencasts/catalog/functional-core-imperative-shell).
  Fowler's [Split Phase](https://refactoring.com/catalog/splitPhase.html)
  demonstrates separating stages with intermediate data.

## Choose a staged migration only when the contract needs one

For a broad interface or data-format replacement within the authorized scope,
consider [Parallel Change](https://martinfowler.com/bliki/ParallelChange.html):
expand support for old and new consumers, migrate them in verified steps, then
remove the old path after identifying every supported consumer. Check both paths
while they coexist and preserve a rollback point for each phase. A database or
published API migration may require separate authority and data or compatibility
proof. Do not start one as a routine cleanup or leave a temporary adapter in
place indefinitely. This complements the Branch by Abstraction technique above.

The per-knot verification and local rollback requirements are Untangle's policy.
The sources support incremental refactoring; they do not prescribe this exact
artifact or Git workflow.

## Proportionate proof

For each knot, record one plausible maintenance edit, the files or rules that
would need to change together before, and which obligations remain afterward.
For a detour, name the real handoffs that were removed. For a shared rule,
identify where the decision now lives and which callers still use it. For a
state boundary, record who owns it and how the checks exercise failure and
cleanup. Verify the scenario against both source revisions.

Review each touched application, support, test, harness, and configuration
module for avoidable work, failure handling, cleanup, and diagnostics. Record
why the existing behavior is adequate when it needs no change. Measure any speed
claim with the same workload and environment before and after. Keep diagnostics
actionable without exposing sensitive data or writing to a machine-readable
result stream.

Reuse existing tests when they cover affected contracts. Add characterization
only for an actual uncovered risk; test outcomes and side effects rather than
private function shapes. Compare old and new outcomes using an independent
expectation or recorded baseline, not two copies of the new implementation.

When useful Git history is available, compare change frequency and files that
repeatedly change together with the actual maintenance problem. Treat that
history as a way to select investigation targets, not as proof that code is
defective. A quiet but critical boundary may still take priority. This adapts
CodeScene's
[hotspot guidance](https://www.codescene.io/docs/guides/technical/hotspots.html)
without requiring the product or a new runtime dependency.

Async state, caches, persistence, and resource lifecycle need failure and
interleaving evidence when affected. A build alone proves neither race safety
nor data equivalence. Avoid load/performance claims from fewer files or lines;
measure the affected workload if such a claim matters.

No amount of diagram cleanliness establishes correctness. Edge reductions, cycle
counts, duplication counts, and ownership consolidation explain the structural
change; tests and contract inspection support preserved behavior.

For unfamiliar language or framework APIs, identify the pinned version from the
project's declarations and lockfile. Check behavior against local documentation,
installed types and source, and existing tests. Record unresolved questions in
the evidence and defer any change that depends on the answer.
