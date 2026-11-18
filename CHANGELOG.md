# Changelog

## 0.1.0

### Skill and renderer

- Tie each fix to a maintenance edit and verify which changes it would require
  before and after. Review affected modules for work, failure handling, cleanup,
  and diagnostics.
- Refuse output paths that pass through Windows junctions or other reparse
  points.
- Show filenames when long paths would hide the distinguishing part of a node
  label. Keep full paths in the evidence inventory.

- Draw complete source-backed detours and their direct replacements with stable
  file positions and numbered handoffs. Use a readable route comparison in the
  README, with the complete wiring map linked alongside it.
- Lead comparisons with the full before/after wiring map and numbered knots,
  marking routes that occur in only one snapshot. Follow with source-based
  diagrams explaining each changed boundary.
- Explain changes with matched source excerpts, responsibility changes,
  preserved behavior, and recorded checks. Keep the full wiring map as context
  and state when its feature/file connections are unchanged.
- Show the pending report dropping two storage handoffs and storage taking over
  JSON on both read and write paths. Check the diagrams against the runnable
  checkout snapshots.
- Map features to files with source locations, coverage limits, and a ranked
  register of maintenance problems.
- Cover six knot categories and the sourced diagnostic and refactoring patterns
  listed in the [README](README.md#patterns-untangle-addresses).
- Support read-only audits and local refactoring with per-knot checkpoints,
  verification, rollback, and observed before-and-after maps.
- Render HTML, SVG, and JSON using Python's standard library. Add validation,
  output previews, structured results, and a CLI result schema.
- Protect existing outputs during writes and handled cancellation. Preserve
  concurrent edits and report recovery copies when restoration cannot complete.
- Validate bounded input before rendering and reject characters invalid in SVG.
- Include a runnable checkout example with source snapshots, shared behavior
  checks, and a generated comparison.

### Installation and participation

- Package one skill with its renderer, references, agent metadata, and MIT
  license. Keep repository tests and development tools outside the installed
  directory.
- Document Codex, Claude Code, Cursor, and GitHub Copilot installation with
  Skills CLI commands for npm and Bun, plus manual installation.
- Provide issue forms for bugs, help, and proposals. Invite pull requests after
  agreeing on the change.
- Document support, sponsorship, security reporting, and the contribution
  process.

### Repository checks

- Share a local and CI gate for formatting, lint, Markdown, package structure,
  local links, renderer tests, and the worked example.
- Use Bun for JavaScript in CI and support both Bun and npm for contributors.
  Pin the formatter and linter locally through both lockfiles.
- Add help, non-writing plans, and structured results to contributor commands.
- Cover renderer cancellation, output recovery, concurrent edits, and launcher
  startup and signal handling without adding runtime dependencies.
- Use the package check to enforce the seven installed files and keep archives
  and development files out of the skill.
- Override the documentation toolchain's KaTeX dependency with a patched release
  for [GHSA-238p-pmpm-9mq7](https://github.com/advisories/GHSA-238p-pmpm-9mq7).
