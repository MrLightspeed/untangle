# Standards and references

These sources inform the package format, installation instructions, refactoring
workflow, and contribution process. The linked projects also provide examples of
how to document a skill for new users.

| Source                                                                                                                                                                                                                                                  | What it demonstrates                                                       | Untangle decision                                                                                            |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| [Vercel Agent Browser](https://github.com/vercel-labs/agent-browser) and its [skills.sh page](https://www.skills.sh/vercel-labs/agent-browser)                                                                                                          | Purpose, installation, and a useful first step near the top of the README. | Keep the README direct and put install and usage near the top.                                               |
| [Matt Pocock's Improve Codebase Architecture skill](https://github.com/mattpocock/skills/tree/main/skills/engineering/improve-codebase-architecture) and its [skills.sh listing](https://www.skills.sh/mattpocock/skills/improve-codebase-architecture) | A single skill with a clear audience, method, and expected result.         | Make Untangle's workflow and limits clear before describing the package.                                     |
| [Agent Skills specification](https://agentskills.io/specification)                                                                                                                                                                                      | Required metadata, optional resources, and portable skill layout.          | Treat it as the authority for structure; keep the skill folder self-contained.                               |
| [Skills CLI agent targets](https://github.com/vercel-labs/skills/blob/main/docs/agents.md) and [commands](https://github.com/vercel-labs/skills/blob/main/docs/commands.md)                                                                             | Supported agent identifiers, install locations, and CLI options.           | Link to current CLI options and distinguish installation from native execution.                              |
| [Claude Code skills](https://code.claude.com/docs/en/skills), [Cursor skills](https://cursor.com/docs/skills), and [GitHub Copilot agent skills](https://docs.github.com/en/copilot/concepts/customizations/agent-skills)                               | Host-specific skill discovery and invocation guidance.                     | Give each host its documented install path and first-use prompt; separate install checks from host behavior. |
| [OpenAI Plugins](https://github.com/openai/plugins) and [packaging guidance](https://developers.openai.com/plugins/build/plugins)                                                                                                                       | Distribution examples and portable plugin manifests.                       | Package one skill under `skills/`; do not imply a directory listing.                                         |
| [Anthropic skills](https://github.com/anthropics/skills) and its [template](https://github.com/anthropics/skills/tree/main/template)                                                                                                                    | Minimal frontmatter and skills with supporting resources.                  | Keep conditional detail in references without requiring one universal skill outline.                         |
| [Blender Skills](https://github.com/arjun988/blender-skills)                                                                                                                                                                                            | Visible installation, contribution, licensing, and usage guidance.         | Make onboarding clear while keeping one canonical Untangle skill.                                            |
| [GitHub PR access settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/disabling-pull-requests)                                                                      | Collaborator-only PR creation with issues managed separately.              | Keep issue intake public and PR creation controlled.                                                         |
| [GitHub secure workflow guidance](https://docs.github.com/en/actions/reference/security/secure-use)                                                                                                                                                     | Minimum token permissions and full-commit action pins.                     | Use read-only CI permissions, pin actions, and do not execute untrusted submissions with privileged access.  |

The example repositories inform presentation and onboarding. The Agent Skills
specification governs the package format; Untangle's
[writing standard](STYLE.md) defines its formatting conventions.

The before-and-after example draws on Martin Fowler's
[definition of refactoring](https://martinfowler.com/bliki/DefinitionOfRefactoring.html)
and
[module dependency refactoring](https://martinfowler.com/articles/refactoring-dependencies.html).
Clear responsibilities and dependency direction explain the structural change;
behavior checks establish whether a real refactor preserves its results.

The README's [patterns section](README.md#patterns-untangle-addresses) cites the
original authors and publisher excerpts for its diagnostics. The installed
[refactoring reference](skills/untangle/references/refactoring-practice.md)
records when sources were checked and explains how Untangle applies each
technique. The category names and proof requirements are this project's
synthesis; the cited sources do not prescribe Untangle's map format or Git
workflow.

Bun's native [formatter](https://bun.com/docs/format) and
[linter](https://bun.com/docs/lint), plus Markdownlint, are repository tooling
choices. The Agent Skills specification does not require them. The formatter
reads the existing Prettier configuration; see the
[configuration guide](https://prettier.io/docs/configuration). Markdownlint
retains its
[Markdown rules](https://github.com/DavidAnson/markdownlint/blob/main/doc/Rules.md).
