# Writing and formatting standard

This is the repository's enforceable house standard. The Agent Skills
specification governs package structure and metadata. It does not prescribe a
universal heading template or Markdown formatter.

## Skill structure

- Keep exactly one canonical skill at `skills/untangle/SKILL.md`.
- Use valid YAML frontmatter with `name: untangle` and a nonempty description of
  at most 1,024 characters. Match the folder name to the skill name.
- Use supported optional metadata only when it serves discovery or portability.
- Keep the entry point under 500 lines. Put detailed schemas and conditional
  procedures in linked references. This is a project limit, not a schema limit.
- Keep references relative and inside the package. Say when to read them.
- Put installation instructions, governance, and release notes at repository
  level.
- Include the MIT license in the repository and installable package.

## All documentation and configuration

Bun's native formatter formats Markdown, YAML, JSON, and JavaScript contributor
tooling using the existing Prettier configuration. Bun's native linter checks
JavaScript; Markdownlint checks Markdown structure. The project-local Bun canary
and other development dependencies are pinned in `package.json`, `bun.lock`, and
`package-lock.json`.

- Use UTF-8, LF line endings, spaces, and a final newline.
- Use one descriptive H1, sequential heading levels, and sentence case headings.
- Separate paragraphs, lists, headings, and fenced blocks with blank lines.
- Give every fenced block a language; use `text` for prompts and file trees.
- Use descriptive link text and repository-relative links for local files.
- Wrap prose at 80 columns with the formatter. Links, tables, and code may
  exceed that width. Markdownlint's line-length rule is disabled to avoid a
  conflicting wrapping policy; the formatter still checks exact layout.
- Keep identifiers and commands exact. Mark tested behavior, examples, and
  requirements clearly.
- Keep instructions durable. Link to `package.json`, the lockfiles, or the CI
  workflow for tool versions instead of copying their current values into prose.
  Use a moving CLI tag for general installation commands and explain how to
  select a fixed source revision. Keep deliberate compatibility requirements,
  schema identifiers, release history, and dated verification records exact.
- Keep badges useful: link to their source, distinguish snapshots from live
  metrics, and state only supported compatibility or release claims. Do not use
  badges as a substitute for installation instructions or verification evidence.

## Prose review

Read public prose for accuracy, clear actions, and a natural speaking rhythm.
Remove stock phrases, repeated explanations, unsupported claims, and decorative
wording. Keep commands, identifiers, and legal meaning exact. Read the copy
aloud, then compare it with the source for changes in meaning or scope.

Use manual review to judge the writing. Do not use AI detector scores to judge
authorship or accept copy.

Use plain punctuation in editable prose. Do not use em dashes. Replace avoidable
compound adjectives with the actual noun, verb, or relationship.

## Checks

Default Markdownlint rules otherwise apply. The checker also verifies local
Markdown targets, package metadata, license parity, and configuration syntax. It
does not validate remote links or heading anchors.

```sh
bun run format
bun run check
```

Contributors using npm can run the same checks from the npm lockfile:

```sh
npm ci --ignore-scripts
npm run format
npm run check
```

The same `check` gate runs in CI. A green formatting check confirms layout
consistency. Review the claims and examples separately. See
[exemplars](REFERENCES.md) for the sources behind these choices.
