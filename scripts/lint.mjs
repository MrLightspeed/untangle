import { runLocalBun } from "./local-bun.mjs";

const help = `Usage: node scripts/lint.mjs [--json]

Check repository JavaScript with the pinned local Bun linter, without fixes.
Markdown rules are checked separately by scripts/check-package.mjs.

Options:
  --json      Write one versioned result to stdout; diagnostics go to stderr.
  -h, --help  Show this help without resolving dependencies or running checks.

Exit codes: 0 success/help; 1 lint errors; 2 invalid arguments; 3 local tool startup failure.
Other child statuses are preserved; child signals use 128 + signal number.
JSON results contain schema_version, command, mode, status, and child_exit_code.
`;

const args = process.argv.slice(2);
const unknown = args.find((arg) => arg !== "--json");
if (args.includes("--help") || args.includes("-h")) {
  process.stdout.write(help);
} else if (unknown !== undefined) {
  const message = `Unsupported lint argument ${JSON.stringify(unknown)}. Valid options are --json and --help. Try: node scripts/lint.mjs --help`;
  if (args.includes("--json")) {
    process.stdout.write(
      JSON.stringify({
        schema_version: "1.0.0",
        command: "lint",
        mode: "error",
        status: "failed",
        child_exit_code: null,
        error: {
          stage: "arguments",
          message,
          recovery: "node scripts/lint.mjs --help",
        },
      }) + "\n",
    );
  } else process.stderr.write(message + "\n");
  process.exitCode = 2;
} else {
  runLocalBun("lint", ["."], { json: args.includes("--json") });
}
