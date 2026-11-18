#!/usr/bin/env node
import { runLocalBun } from "./local-bun.mjs";

const help =
  [
    "Usage: node scripts/format.mjs [--check | --write] [--json]",
    "",
    "Format the repository with its pinned local Bun formatter.",
    "",
    "Options:",
    "  --check   Check formatting without changing files (default).",
    "  --write   Format files in place.",
    "  --json    Write one stable result object to stdout.",
    "  -h, --help  Show this help before resolving dependencies.",
    "",
    "Exit codes:",
    "  0  The check or write completed successfully.",
    "  1  Bun reported unformatted files.",
    "  2  Invalid arguments or Bun formatting errors.",
    "  3  The local Bun formatter could not be resolved or started.",
    "  Other child statuses are preserved; signals use 128 + signal number.",
  ].join("\n") + "\n";

function parseArguments(arguments_) {
  const json = arguments_.includes("--json");
  if (
    arguments_.some((argument) => argument === "--help" || argument === "-h")
  ) {
    return { help: true };
  }

  let check = false;
  let write = false;
  for (const argument of arguments_) {
    if (argument === "--check") {
      check = true;
    } else if (argument === "--write") {
      write = true;
    } else if (argument !== "--json") {
      return {
        json,
        mode: "error",
        error: `Unknown argument ${JSON.stringify(argument)}. Remove it; valid options are --check, --write, and --json.`,
      };
    }
  }

  if (check && write) {
    return {
      json,
      mode: "error",
      error:
        "Conflicting options --check and --write. Remove --write to check, or remove --check to format.",
    };
  }

  return { json, mode: write ? "write" : "check" };
}

function resultObject(mode, status, childExitCode, error) {
  const result = {
    schema_version: "1.0.0",
    command: "format",
    mode,
    status,
    child_exit_code: childExitCode,
  };
  if (error) {
    result.error = error;
  }
  return result;
}

function emitJson(result) {
  process.stdout.write(JSON.stringify(result) + "\n");
}

function reportArgumentFailure(message, json) {
  if (json) {
    emitJson(
      resultObject("error", "failed", null, {
        stage: "arguments",
        message,
        recovery: "Try: node scripts/format.mjs --help",
      }),
    );
  } else {
    process.stderr.write(message + "\nTry: node scripts/format.mjs --help\n");
  }
  process.exitCode = 2;
}

const parsed = parseArguments(process.argv.slice(2));
if (parsed.help) {
  process.stdout.write(help);
} else if (parsed.mode === "error") {
  reportArgumentFailure(parsed.error, parsed.json);
} else {
  runLocalBun(
    "fmt",
    parsed.mode === "write" ? ["."] : ["--check", "."],
    parsed,
  );
}
