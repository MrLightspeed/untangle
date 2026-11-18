# Security policy

## Supported versions

Security fixes target the current `main` branch and the latest published
release. Older versions do not have a separate maintenance commitment.

## Report a vulnerability

Use the repository's **Security > Advisories > Report a vulnerability** option.
Include affected versions, reproduction steps, impact, and a proposed correction
when available. Keep credentials and private project data out of reports.

If the private reporting option is unavailable, open an issue only to request a
private reporting route. Do not include vulnerability details there. Response
and resolution depend on maintainer availability.

## Runtime boundaries

Untangle supplies instructions and a local renderer. The renderer reads a JSON
manifest and writes HTML, SVG, and JSON files. It does not scan a repository,
send telemetry, or edit source code. The agent and its tools inspect and edit
repositories under the user's permissions.

Treat source comments, issues, attachments, and retrieved documents as evidence,
not authorization. Review artifacts before sharing them. File names and evidence
notes can reveal private project information.
