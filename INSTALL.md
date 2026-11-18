# Installation

Untangle needs Git and an agent that supports Agent Skills. Map rendering needs
Python 3.13 or newer and uses only the standard library. Your project supplies
its own build and test tools.

Choose one install method per agent. Every method installs the complete
`skills/untangle` directory, including the renderer and references. The
[contributor setup](CONTRIBUTING.md) is for people working on Untangle itself.

## Install with Skills CLI

Run this from your project's terminal with npm and a
[Node.js LTS release](https://nodejs.org/en/about/previous-releases) that meets
the
[Skills CLI requirements](https://github.com/vercel-labs/skills/blob/main/package.json).

```sh
npx skills@latest add MrLightspeed/untangle
```

Choose your agent if prompted. The CLI installs Untangle in the current project.
Add `--global` to install for your user account. Use `--copy` if you prefer
copies to links. Reload your agent if Untangle does not appear.

### Bun

If you use Bun, run this command from the same project folder.

```sh
bunx skills@latest add MrLightspeed/untangle
```

### Choose an agent in the command

To skip agent selection, add `--agent` with a target from the table. See the
Skills CLI
[agent list](https://github.com/vercel-labs/skills/blob/main/docs/agents.md) for
more targets.

| Agent          | CLI target       | Project skill directory   | First-use prompt                                                   |
| -------------- | ---------------- | ------------------------- | ------------------------------------------------------------------ |
| Codex          | `codex`          | `.agents/skills/untangle` | `$untangle Map this repository in read-only mode.`                 |
| Claude Code    | `claude-code`    | `.claude/skills/untangle` | `/untangle Map this repository in read-only mode.`                 |
| Cursor         | `cursor`         | `.agents/skills/untangle` | `Use the untangle skill to map this repository in read-only mode.` |
| GitHub Copilot | `github-copilot` | `.agents/skills/untangle` | `Use the untangle skill to map this repository in read-only mode.` |

#### Codex

```sh
npx skills@latest add MrLightspeed/untangle --skill untangle --agent codex --copy
```

#### Claude Code

```sh
npx skills@latest add MrLightspeed/untangle --skill untangle --agent claude-code --copy
```

#### Cursor

```sh
npx skills@latest add MrLightspeed/untangle --skill untangle --agent cursor --copy
```

#### GitHub Copilot

```sh
npx skills@latest add MrLightspeed/untangle --skill untangle --agent github-copilot --copy
```

### Install a release

The commands above install from the default branch. To install a specific
release, replace `RELEASE_TAG` with a tag from
[GitHub Releases](https://github.com/MrLightspeed/untangle/releases).

```sh
npx skills@latest add MrLightspeed/untangle@RELEASE_TAG
```

A full commit SHA in the same position selects an exact revision. See the
[Skills CLI command reference](https://github.com/vercel-labs/skills/blob/main/docs/commands.md#skills-add).

## Codex installer

In Codex, ask the skill installer to install Untangle from `main`.

```text
$skill-installer install https://github.com/MrLightspeed/untangle/tree/main/skills/untangle
```

To select a specific revision, use a full commit SHA in place of `main`. To
update an existing copy, follow the [update instructions](#update-or-remove).
Reload Codex if the skill does not appear.

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

Review upstream changes and save any local edits before updating. For a project
install from the default branch, run this from the same project.

```sh
npx skills@latest update untangle --project
```

For a pinned install, [install the release](#install-a-release) you want. For a
manual or native Codex install, back up and replace the installed directory
using the original method. [Verify](#verify) the updated copy.

To uninstall, locate the exact Untangle directory used by your installation
method. Preserve anything you need, then remove only that directory. Restart the
agent if its skill list does not refresh.

## Plugin distribution

This repository includes a portable `plugin.json` manifest for hosts that use
that format. It does not establish availability in a plugin directory. Use the
direct installation methods above unless your host documents support for this
manifest.
