# Installation

Install the complete `skills/untangle` directory. Copying only `SKILL.md` leaves
out the renderer and references. Choose one installation method so you do not
end up with duplicate skills of the same name.

Use Python 3.13 or newer to render maps. The renderer uses only Python's
standard library. There are no third-party Python or JavaScript packages to
install for the skill itself. Git and an agent that supports Agent Skills are
also required; the project you refactor keeps its own build and test tools.

Install the skill directory without running `npm install` or `bun install` in
the source repository. Node.js or Bun is needed only for the optional Skills CLI
installer below. Repository development dependencies and tests are for
[contributors](CONTRIBUTING.md).

## Codex installer

In Codex, ask the skill installer to install Untangle from `main`:

```text
$skill-installer install https://github.com/MrLightspeed/untangle/tree/main/skills/untangle
```

The default branch can change as development continues. For an immutable source,
use a full commit SHA. Installation does not update an existing copy. Restart
Codex if the skill does not appear.

## Install with Skills CLI

The [Skills CLI](https://github.com/vercel-labs/skills) installs the package in
the current project and selects a destination for each agent. The commands use
`skills@latest`, which resolves the newest published CLI when you run them. For
current command options and agent targets, see the CLI's
[command reference](https://github.com/vercel-labs/skills/blob/main/docs/commands.md)
and
[agent list](https://github.com/vercel-labs/skills/blob/main/docs/agents.md).

| Agent          | CLI target       | Project skill directory   | First-use prompt                                                   |
| -------------- | ---------------- | ------------------------- | ------------------------------------------------------------------ |
| Codex          | `codex`          | `.agents/skills/untangle` | `$untangle Map this repository in read-only mode.`                 |
| Claude Code    | `claude-code`    | `.claude/skills/untangle` | `/untangle Map this repository in read-only mode.`                 |
| Cursor         | `cursor`         | `.agents/skills/untangle` | `Use the untangle skill to map this repository in read-only mode.` |
| GitHub Copilot | `github-copilot` | `.agents/skills/untangle` | `Use the untangle skill to map this repository in read-only mode.` |

Use a supported
[Node.js LTS release](https://nodejs.org/en/about/previous-releases) with npm
that meets the
[Skills CLI runtime requirements](https://github.com/vercel-labs/skills/blob/main/package.json).
Bun is not required. Run the command for your agent from your project's root:

### Codex

```sh
npx skills@latest add MrLightspeed/untangle --skill untangle --agent codex --copy
```

### Claude Code

```sh
npx skills@latest add MrLightspeed/untangle --skill untangle --agent claude-code --copy
```

### Cursor

```sh
npx skills@latest add MrLightspeed/untangle --skill untangle --agent cursor --copy
```

### GitHub Copilot

```sh
npx skills@latest add MrLightspeed/untangle --skill untangle --agent github-copilot --copy
```

These commands install from the default branch into the current project. Add
`--global` to install for your user account instead. Use one installation method
to avoid duplicate skills, and preserve existing local edits before updating.

To use Bun instead of npm, replace `npx` with `bunx` in the command for your
agent. `--copy` installs a copy of the skill files. The host may need to reload
its skills list before Untangle appears.

Codex prompts use `$untangle`; Claude Code supports `/untangle`. For Cursor and
GitHub Copilot, ask in chat using the prompt above. See the host documentation
in [References](REFERENCES.md).

## Manual installation

Clone the repository and record the commit you are installing:

```sh
git clone https://github.com/MrLightspeed/untangle.git untangle-source
cd untangle-source
git rev-parse HEAD
```

The command prints the full commit SHA. To install a specific commit, check it
out before copying:

```sh
git checkout --detach <full-commit>
```

The following examples install into the user's `.agents/skills` directory for
Codex. For a project-only Codex installation, use that project's
`.agents/skills` as the destination root. Use the Skills CLI above for other
agents so the files go to the host's project skill directory.

### macOS and Linux

Run from the clone's root in a shell with `set -e` support:

```sh
set -e
skill_root="$HOME/.agents/skills"
destination="$skill_root/untangle"
if [ -e "$destination" ] || [ -L "$destination" ]; then
  echo "Untangle already exists. Preserve and review it before updating."
  exit 1
fi
mkdir -p "$skill_root"
cp -R skills/untangle "$destination"
```

### Windows PowerShell

Run from the clone's root:

```powershell
$ErrorActionPreference = 'Stop'
$skillRoot = Join-Path $HOME '.agents/skills'
$destination = Join-Path $skillRoot 'untangle'
if (Test-Path -LiteralPath $destination) {
    throw 'Untangle already exists. Preserve and review it before updating.'
}
New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null
Copy-Item -LiteralPath 'skills/untangle' -Destination $destination -Recurse
```

Other Agent Skills hosts can use this package in their documented skill
location. See [compatibility](#compatibility) for what has been tested.

## Verify

Confirm that the installed directory contains `SKILL.md`, `LICENSE.txt`,
`agents/openai.yaml`, `references/`, and `scripts/render_map.py`. Confirm that
the renderer loads with your installed path:

```sh
python /path/to/untangle/scripts/render_map.py --help
```

Ask your agent for a read-only audit of a small repository you own. It should
produce a baseline map and recommendations without editing code or creating a
branch. Repository contributors run the renderer regression tests through the
[contributor check](CONTRIBUTING.md). Those tests verify the helper rather than
an agent's feature tracing or refactoring decisions.

## Compatibility

The package follows the
[Agent Skills specification](https://agentskills.io/specification). Local-path
installs through the Skills CLI were checked for the four targets above: each
copied the seven skill files without repository development packages, and the
copied renderer ran with Python's site packages disabled. These checks covered
local copying and renderer startup, not GitHub downloads or native agent
execution.

A scoped read-only audit was completed in Codex. In a separate coding-agent
pilot, the agent used a pinned copy of the skill to refactor an isolated Python
project and recover from a deliberate test failure. The pilot covered one
subsystem. GitHub Copilot loaded the skill and wrote audit evidence, but its
tool permissions blocked tests and rendering. Native audits in Claude Code and
Cursor and a full-repository agent run remain unverified. The
[CI workflow](.github/workflows/check.yml) runs package and renderer checks on
Windows and Linux.

If your host supports Agent Skills, start with the small read-only audit above.
Maintainers testing a host can follow the
[native host check procedure](MAINTAINING.md#native-host-checks).

## If an audit is interrupted

Preserve any logs, evidence manifests, and generated maps. Confirm that the
source files still match the recorded revision, then ask the agent to resume
from its last completed step. If a valid manifest already exists, it can render
the map without repeating discovery. Review any helper the agent wrote before
running it. See [support](SUPPORT.md) if the same step keeps failing.

## Update or remove

An installation is a snapshot. Review upstream changes, keep any local
customizations, and back up the exact installed directory before replacing it.
Run the checks again. This repository provides no command that silently
overwrites an installed skill.

To uninstall, locate the exact Untangle directory used by your installation
method. Preserve anything you need, then remove only that directory. Restart the
agent if its skill list does not refresh.

## Plugin distribution

This repository includes a portable `plugin.json` manifest for hosts that use
that format. It does not establish availability in a plugin directory. Use the
direct installation methods above unless your host documents support for this
manifest.
