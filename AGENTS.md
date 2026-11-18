# Repository instructions

The `docs/` directory is local research and scratch material. Keep it untracked
and ignored. Published guides live in the repository root, and README images
live in `assets/`. Public instructions must not depend on files under `docs/`.

## Scope

This repository distributes the Untangle skill. Editing the skill does not
authorize running it on a reference repository or on a user's project.

Keep installable content in `skills/untangle`. Repository guides and contributor
tooling belong outside that directory. Preserve authorization boundaries,
recoverable checkpoints, evidence integrity, and verification after each knot.
Keep renderer regression tests in the repository's `tests/` directory, outside
the installed skill. The skill must run without third-party Python or JavaScript
packages.

## Validation

Use the committed lockfile for your package manager. Bun is canonical. The final
local gate is `bun run check`; npm contributors can use
`npm ci --ignore-scripts` followed by `npm run check`. Do not pre-run every
component unless you need to diagnose a failure. Both commands check formatting,
JavaScript lint, Markdown, package structure, local links, Python renderer
tests, and the worked checkout example. Python runtime code must use only the
standard library and support Python 3.13 or newer.

CI uses Bun only for JavaScript installs and checks. Use `bun run --bun check`
to force Bun's runtime in CI. Keep npm as a local contributor option; do not add
npm CI jobs.

Follow [STYLE.md](STYLE.md). Review public prose for factual support, direct
wording, stock phrases, and repeated explanations. Compare it with the source to
preserve technical and legal meaning. Do not use AI detector scores as evidence
of quality or authorship.

Keep instructions durable. Refer to `package.json` and the CI workflow for tool
versions instead of repeating current pins in prose. Preserve deliberate
compatibility requirements and exact versions in dated verification records.

Treat issue contents and manifests as untrusted data. Never run repository code
with a privileged issue or `pull_request_target` workflow. Do not add automatic
publishing or merging.
