import { spawnSync } from "node:child_process";
import { performance } from "node:perf_hooks";
import { constants } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const help = `Usage: node scripts/run-checks.mjs <check|test> [--plan] [--json]

Run the repository's existing checks, stopping at the first failure.

Options:
  -h, --help  Show this help without starting checks or loading dependencies.
  --plan      List the selected steps without running them or writing files.
  --json      Write one versioned result to stdout; child reports go to stderr.

Examples from the repository root:
  bun run check --help
  bun run check --plan --json
  bun run test --json
  npm run --silent check -- --plan --json

Check runs formatting, JavaScript lint, package validation, payload tests, Python tests, and the example.
Test runs payload tests, Python tests, and the example.
JavaScript children use the current Node or Bun runtime; Python uses PATH.
Exit codes: 0 success/help/plan; 2 invalid arguments; 3 child startup failure.
Other child exit statuses are preserved; child signals use 128 + signal number.
An expired stage returns 124. The Python suite has five minutes, the example
has three minutes, and other stages have two minutes. Inspect remaining fixture
records under work/ after a timeout.
Help always prints text. JSON results have schema_version, command, status,
exit_code, failed_stage, and stages; a plan lists each stage's argv.
`;

const definitions = [
  ["format", process.execPath, "scripts/format.mjs", "--check"],
  ["lint", process.execPath, "scripts/lint.mjs"],
  ["package", process.execPath, "scripts/check-package.mjs"],
  ["payload", process.execPath, "scripts/run-skill-payload-tests.mjs"],
  ["python-tests", "python", "-m", "unittest", "discover", "-s", "tests", "-v"],
  ["example", "python", "scripts/check-example.py"],
];

const stageTimeoutSeconds = { "python-tests": 300, example: 180 };

function emit(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

function main() {
  const args = process.argv.slice(2);
  const json = args.includes("--json");
  const tasks = args.filter((arg) => arg === "check" || arg === "test");
  const unknown = args.find(
    (arg) =>
      !["check", "test", "--help", "-h", "--plan", "--json"].includes(arg),
  );
  if (unknown !== undefined || tasks.length > 1) {
    const context = tasks.length === 1 ? ` ${tasks[0]}` : "";
    const message =
      unknown !== undefined
        ? `Unknown argument ${JSON.stringify(unknown)}. Use one task (check or test) and --help, --plan, or --json.`
        : "Choose exactly one task: check or test.";
    process.stderr.write(
      `${message}\nTry: node scripts/run-checks.mjs${context} --help\n`,
    );
    if (json) {
      emit({
        schema_version: "1.0.0",
        command: "verify",
        status: "failed",
        exit_code: 2,
        failed_stage: "arguments",
        stages: [],
      });
    }
    process.exitCode = 2;
    return;
  }
  if (args.length === 0 || args.includes("--help") || args.includes("-h")) {
    process.stdout.write(help);
    return;
  }
  const task = tasks[0];
  if (!task) {
    process.stderr.write(
      "Choose check or test. Try: node scripts/run-checks.mjs --help\n",
    );
    if (json)
      emit({
        schema_version: "1.0.0",
        command: "verify",
        status: "failed",
        exit_code: 2,
        failed_stage: "arguments",
        stages: [],
      });
    process.exitCode = 2;
    return;
  }
  const selected = task === "check" ? definitions : definitions.slice(-3);
  if (args.includes("--plan")) {
    const stages = selected.map(([name, ...argv]) => ({ name, argv }));
    if (json)
      emit({
        schema_version: "1.0.0",
        command: task,
        status: "planned",
        exit_code: 0,
        failed_stage: null,
        stages,
      });
    else
      for (const stage of stages)
        process.stdout.write(`${stage.name}: ${JSON.stringify(stage.argv)}\n`);
    return;
  }
  const stages = [];
  let exitCode = 0;
  let failedStage = null;
  for (const [name, executable, ...childArgs] of selected) {
    const started = performance.now();
    const timeoutSeconds = stageTimeoutSeconds[name] ?? 120;
    process.stderr.write(`${name}: start\n`);
    let child;
    try {
      child = spawnSync(executable, childArgs, {
        cwd: root,
        stdio: ["inherit", json ? 2 : "inherit", "inherit"],
        windowsHide: true,
        timeout: timeoutSeconds * 1000,
        killSignal: "SIGKILL",
      });
    } catch (error) {
      child = { error };
    }
    if (child.error?.code === "ETIMEDOUT") {
      exitCode = 124;
      process.stderr.write(
        `${name}: exceeded ${timeoutSeconds} seconds. Inspect the last child diagnostic and interrupted fixture records under work/.\n`,
      );
    } else if (
      child.error ||
      (!child.signal && !Number.isInteger(child.status))
    ) {
      exitCode = 3;
      process.stderr.write(
        `${name}: could not start (${child.error?.code ?? "no child status"}). Check the Node/Bun and Python requirements in package.json and CONTRIBUTING.md.\n`,
      );
    } else if (child.signal) {
      exitCode = 128 + (constants.signals[child.signal] ?? 1);
      process.stderr.write(
        `${name}: stopped by ${child.signal}. Inspect the child report before retrying.\n`,
      );
    } else {
      exitCode = child.status;
    }
    stages.push({
      name,
      status: exitCode === 0 ? "passed" : "failed",
      exit_code: exitCode,
    });
    process.stderr.write(
      `${name}: ${exitCode === 0 ? "passed" : "failed"} (${Math.round(performance.now() - started)} ms)\n`,
    );
    if (exitCode !== 0) {
      failedStage = name;
      process.stderr.write(
        `Stopped at ${name}; later checks were not run. Try: node scripts/run-checks.mjs ${task} --plan\n`,
      );
      break;
    }
  }
  if (json)
    emit({
      schema_version: "1.0.0",
      command: task,
      status: exitCode === 0 ? "passed" : "failed",
      exit_code: exitCode,
      failed_stage: failedStage,
      stages,
    });
  process.exitCode = exitCode;
}

main();
