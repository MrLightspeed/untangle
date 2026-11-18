import { constants as osConstants } from "node:os";
import childProcess from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const testFile = "tests/skill-payload.test.mjs";
const help = `Usage: node scripts/run-skill-payload-tests.mjs [--help]
       node scripts/run-skill-payload-tests.mjs

Run the installable skill payload tests with the current Node or Bun runtime.
No arguments runs the canonical ${testFile} suite.

Commands:
  bun run test  Canonical local test command.
  npm test      Locked npm contributor option.
  node scripts/run-skill-payload-tests.mjs

Exit codes:
  0  Help was shown or the child test suite passed.
  2  Invalid arguments (a child exit status of 2 is preserved).
  3  The selected runtime could not be started.
  124  The child test suite exceeded its 90-second deadline.
  Other child exit statuses are preserved; signal exits use 128 + signal number.
`;

function usageError(argument) {
  process.stderr.write(
    `Unknown argument: ${JSON.stringify(argument)}\nTry: node scripts/run-skill-payload-tests.mjs --help\n`,
  );
  process.exitCode = 2;
}

function launchError(runtime, code) {
  process.stderr.write(
    `Could not start the selected ${runtime} test runner (${code}).\n` +
      `Try: ${runtime === "Bun" ? "bun run test" : "npm test"}\n`,
  );
  process.exitCode = 3;
}

function signalExitCode(signal) {
  return 128 + (osConstants.signals[signal] ?? 1);
}

function signalError(runtime, signal) {
  const code = signalExitCode(signal);
  process.stderr.write(
    `The selected ${runtime} test runner was interrupted by ${signal} (exit ${code}).\n` +
      `Try: ${runtime === "Bun" ? "bun run test" : "npm test"}\n`,
  );
  process.exitCode = code;
}

function main() {
  const args = process.argv.slice(2);
  if (args.length === 1 && (args[0] === "--help" || args[0] === "-h")) {
    process.stdout.write(help);
    return;
  }
  if (args.length > 0) {
    usageError(args[0]);
    return;
  }

  const usesBun = Boolean(process.versions.bun);
  const runtime = usesBun ? "Bun" : "Node";
  const executable = process.execPath;

  const childArgs = usesBun
    ? ["test", "./tests/skill-payload.test.mjs"]
    : ["--test", testFile];
  let result;
  try {
    result = childProcess.spawnSync(executable, childArgs, {
      cwd: root,
      stdio: "inherit",
      windowsHide: true,
      timeout: 90_000,
      killSignal: "SIGKILL",
      // Bun's --bun mode can name this executable node; retain Bun CLI parsing.
      argv0: usesBun ? "bun" : undefined,
    });
  } catch (error) {
    launchError(runtime, error?.code ?? "spawn failed");
    return;
  }
  if (result.error?.code === "ETIMEDOUT") {
    console.error(
      "Payload tests exceeded 90 seconds. Inspect tests/skill-payload.test.mjs and interrupted fixture records under work/.",
    );
    process.exitCode = 124;
    return;
  }
  if (result.error) {
    launchError(runtime, result.error.code ?? "spawn failed");
    return;
  }
  if (result.signal) {
    signalError(runtime, result.signal);
    return;
  }
  if (Number.isInteger(result.status)) {
    process.exitCode = result.status;
    return;
  }

  launchError(runtime, "child exited without a status");
}

main();
