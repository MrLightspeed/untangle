# Maintainer guide

Use this guide to manage repository access, issue intake, host checks, and
releases. Git files describe project policy; repository visibility, Actions,
security reporting, and pull request access are controlled in GitHub settings.
Check the live settings before changing them.

## Prepare the repository for public access

Before changing repository visibility, confirm the following:

1. Review the commit that will be published. Confirm the repository and skill
   license files match, and run the required CI checks on that commit.
2. Allow issues from all users. Set pull request creation to collaborators only
   where GitHub offers that setting. Otherwise, use a concurrent pull request
   cap and review by invitation. Temporary interaction limits also restrict
   issues and comments. See
   [GitHub interaction limits](https://docs.github.com/en/communities/moderating-comments-and-conversations/limiting-interactions-in-your-repository).
3. Enable private vulnerability reporting and confirm the report path works.
4. Set Actions' default token permission to read-only. Require approval for
   workflows from outside collaborators and prevent Actions from approving pull
   requests.
5. Protect `main` with a ruleset. Require pull requests, the current CI checks,
   resolved conversations, and restrictions on force pushes and branch deletion.
   Confirm required check names against a completed workflow run. Use an
   independent approval rule only when the project has another trusted reviewer
   available.
6. Review the issue chooser, installation instructions, support and security
   policies, license, and contributor guidance.
7. Confirm the public files contain no credentials, private project details, or
   local research.

Apply changes through GitHub's repository settings. Updating a configuration
file does not change the live setting.

## Manage issue intake

Review issues when capacity allows. Search for duplicates, link related reports,
and decline work that does not fit the project's scope. Accept only as much work
as can be reviewed. Leave reproducible reports open; do not close them only for
inactivity.

For a proposed change, agree on the smallest useful scope before inviting
substantial work. External contributors can share a fork or commit in the issue.
Review the diff before fetching or running it. If the patch is useful, import it
to a maintainer branch and credit its author. An accepted issue does not grant
repository access. Reserve collaborator access for ongoing maintenance.

Use GitHub notification settings to follow issues and reviews at a sustainable
pace. Do not close old issues or send automated messages without a clear reason.
Adjust pull request intake when the project can review more contributions.

## Native host checks

Installation checks show which skill files reach an agent. A native host check
shows whether that agent discovers the installed skill, follows its audit
instructions, and produces valid output. Neither check establishes that an agent
can refactor code or roll back a change.

1. Use a disposable Git project with a small code example, documented tests, and
   a build check. The [worked checkout example](examples/README.md) is a safe
   option. Record the project branch, commit, source hashes, and skill revision
   before the check.
2. Install the skill in that project with one method from
   [the installation guide](INSTALL.md). Start a fresh session in the native
   agent host and use its first-use prompt from that guide.
3. Request a read-only audit. Ask the agent to write a baseline map with
   `after: null`, run the documented tests and build check, and report the skill
   path, source locations, coverage limits, and blocked steps. Tell it not to
   edit source, create a branch or commit, install dependencies, or publish.
4. Confirm the agent loaded the project copy, traced the relevant entry points,
   ran the documented checks, and produced a valid manifest, HTML map, and SVG.
   Confirm that the recorded branch, commit, and source hashes did not change.
5. Record the host and version, skill revision, prompt, checks, output, and
   failures. If a step is blocked, record the block instead of inferring a
   successful result.

If an audit is interrupted, inspect the last completed action and any existing
artifacts before restarting. Validate a complete manifest with the renderer and
continue from the first unfinished step. Keep the audit read-only.

A read-only host check covers skill discovery, loading, audit instructions, and
map output for the tested host and project. It does not test refactoring,
rollback, every host feature, or another agent host. Test those behaviors
separately before making claims about them. Keep compatibility statements tied
to the host, workflow, and result you observed.

To test refactoring, start a fresh session on an isolated, authorized checkout.
Use a case where you can name the maintenance problem and verify the changed
behavior from an independent baseline. Record whether the agent found the cause,
mapped it before editing, and verified the fix. Use a healthy code path as a
control for unnecessary edits.

To test recovery, first verify one successful knot. Then force a check failure
on a second disposable edit. Compare the failed edit's restored files and
behavior with its checkpoint. Confirm that the earlier fix and a neighboring
unrelated file survived. Keep the failure and recovery evidence with the before
and after maps.

## Maintain README badges

Use live badges for stars and releases once the repository is public. Verify
that the images render and that each badge links to its matching GitHub page.
Keep the CI badge linked to the workflow.

The current badge service URLs are:

| Metric         | Image URL                                                                                                                                                |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Stars          | `https://img.shields.io/github/stars/MrLightspeed/untangle?style=for-the-badge&labelColor=0b1220&color=f5be78`                                           |
| CI on main     | `https://img.shields.io/github/actions/workflow/status/MrLightspeed/untangle/check.yml?branch=main&style=for-the-badge&label=Bun%20CI&labelColor=0b1220` |
| Latest release | `https://img.shields.io/github/v/release/MrLightspeed/untangle?style=for-the-badge&labelColor=0b1220&color=c4b5fd`                                       |

Never put access tokens in badge URLs. See Shields' documentation for
[repository stars](https://shields.io/badges/git-hub-repo-stars) and
[workflow status](https://shields.io/badges/git-hub-actions-workflow-status).

## Release a version

1. Select the reviewed commit. Install from the Bun or npm lockfile and run
   `check`. The package check enforces the approved installable file inventory,
   including the license. Confirm each installed file is needed by the skill.
2. Confirm all required CI checks passed on that exact commit. CI uses Bun for
   JavaScript installs and checks; npm remains a local contributor option. Keep
   branch protection aligned with the current check names.
3. Keep the version fields in `plugin.json` and `package.json` aligned. When
   changing package metadata or dependencies, update both lockfiles and test the
   affected behavior. Review dependency overrides before removing them. Write
   release notes that explain behavior changes, compatibility, and known limits.
   Use semantic versions.
4. Create the matching `vX.Y.Z` tag and GitHub release through the authorized
   release process. The installable skill directory is `skills/untangle`.
5. Install the tagged version into a fresh, disposable skill directory and
   verify it. Run the [native host check](#native-host-checks) for each host
   available during release testing. Record unavailable hosts and blocked
   checks. Document `main` as the development branch.

The root plugin manifest describes a distribution option. It does not guarantee
approval or discovery in a public catalog. Submit to a catalog only when the
project chooses to support that distribution.
