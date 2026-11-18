# Contributing

Start with a specific problem, a small example, or a focused improvement. Search
existing issues before opening a new one.

## Discuss the change

Use the bug report form for a reproducible problem, the help form for an
installation or usage question, and the proposal form for an improvement. Use
the example form to share a wiring map or refactor that others can learn from.
Remove credentials, private source, and identifying project details. For a
security concern, follow [the security policy](SECURITY.md).

Describe the problem and the smallest useful outcome. Wait for the maintainer to
agree on scope before doing substantial implementation work. An issue starts a
discussion; it does not assign work or promise a response, review, or release.
The maintainer may decline changes that add complexity or cannot be reviewed
with available time.

## Share a change

Wait for the maintainer to invite a pull request. You can share a fork or commit
link in the agreed issue. Keep the change focused and include the following.

- The issue and agreed scope.
- What changed and why, including any changed contract.
- The checks you ran and their results.
- A small reproduction or output sample when it helps review.
- Any AI assistance and how you checked the change.

The maintainer may import an agreed patch into a maintainer branch, crediting
the contributor and preserving authorship where practical. Issue discussion does
not grant repository access. Collaborator access is for ongoing maintenance.

## Set up and check changes

The installed skill needs Git, an agent that supports Agent Skills, and Python
3.13 or newer for map rendering. The renderer uses Python's standard library.
The JavaScript tools below are for repository maintenance.

Use the package manager and lockfile declared by the repository. Bun is the
canonical setup:

```sh
bun install --frozen-lockfile --ignore-scripts
bun run check
```

npm is also supported. Use an active Node.js LTS release that meets the
`engines` range in `package.json`:

```sh
npm ci --ignore-scripts
npm run check
```

Both package managers install the project-local Bun used for formatting and
linting. npm contributors do not need Bun on `PATH`. Keep optional dependencies
enabled so the platform binary is installed.

Use one package manager for setup and checks. Both workflows run formatting,
JavaScript lint, Markdown and package checks, renderer tests, and the worked
example. The `check` command stops at the first failure. Run
`bun run check --help` or `npm run check -- --help` to see its options. Run
`bun run format` or `npm run format` to apply formatting before checking again.
The check command reports formatting issues without applying fixes. If a check
times out, the command names the stage and stops before running later checks.
Inspect its last diagnostic and any interrupted fixture records under `work/`
before retrying. Finished test fixtures are cleaned up by the test harness.

For focused feedback, `bun run test` or `npm run test` runs the package payload,
renderer tests, and worked example. Use `--help` on a command to see its current
options. CI uses Bun; npm is a local contributor option.

When reporting agent behavior, name the host and workflow you tested and follow
the [native host check](MAINTAINING.md#native-host-checks). An installation
check alone does not establish that an agent follows the skill instructions.

Keep repository tooling and tests outside `skills/untangle`. That directory is
the installable package and contains only files required by the skill. Read
[the writing standard](STYLE.md) before changing public prose or examples.

## Review and licensing

The maintainer chooses what to review and manages releases. Passing checks do
not guarantee acceptance. Changes to workflows, permission boundaries,
licensing, or refactoring and rollback policy need maintainer review.

By submitting material for inclusion, you confirm that you have the right to
contribute it and agree to license it under the repository's MIT license. Keep
third-party notices and attribution. No separate contributor license agreement
is required.
