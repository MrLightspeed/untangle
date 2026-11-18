import { spawn } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { constants } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const setup =
  "bun install --frozen-lockfile --ignore-scripts or npm ci --ignore-scripts";

function linuxLibc() {
  if (process.report?.getReport) {
    const previous = process.report.excludeNetwork;
    try {
      process.report.excludeNetwork = true;
      const header = process.report.getReport().header;
      if (header) return header.glibcVersionRuntime ? "glibc" : "musl";
    } catch {
      // Some runtimes do not implement process reports.
    } finally {
      process.report.excludeNetwork = previous;
    }
  }
  return existsSync("/etc/alpine-release") ? "musl" : "glibc";
}

export function resolveLocalBun({
  root = repositoryRoot,
  platform = process.platform,
  arch = process.arch,
  libc,
} = {}) {
  const read = (file) => JSON.parse(readFileSync(file, "utf8"));
  const project = read(path.join(root, "package.json"));
  const metadata = read(path.join(root, "node_modules", "bun", "package.json"));
  if (
    metadata.name !== "bun" ||
    typeof metadata.version !== "string" ||
    metadata.version.split("+")[0] !==
      project.devDependencies?.bun?.split("+")[0]
  ) {
    throw new Error("The local Bun package does not match package.json.");
  }
  const os = {
    win32: "windows",
    darwin: "darwin",
    linux: "linux",
    freebsd: "freebsd",
    android: "linux",
  }[platform];
  const cpu = { x64: "x64", arm64: "aarch64" }[arch];
  if (!os || !cpu)
    throw new Error("No local Bun package is configured for this platform.");
  const suffix =
    platform === "android"
      ? "-android"
      : platform === "linux" && (libc ?? linuxLibc()) === "musl"
        ? "-musl"
        : "";
  const packageName = `@oven/bun-${os}-${cpu}${suffix}`;
  const expected = metadata.optionalDependencies?.[packageName];
  if (typeof expected !== "string")
    throw new Error("The Bun package does not declare this platform binary.");
  const directory = path.join(root, "node_modules", ...packageName.split("/"));
  const binaryMetadata = read(path.join(directory, "package.json"));
  if (
    binaryMetadata.name !== packageName ||
    binaryMetadata.version.split("+")[0] !== expected.split("+")[0]
  ) {
    throw new Error(
      "The local Bun platform package does not match the pinned package.",
    );
  }
  const executable = path.join(
    directory,
    "bin",
    platform === "win32" ? "bun.exe" : "bun",
  );
  if (!statSync(executable).isFile())
    throw new Error("The local Bun platform executable is missing.");
  return { executable, packageName, packageVersion: metadata.version };
}

export function runLocalBun(
  command,
  args,
  { json = false, mode = "check" } = {},
) {
  const name = command === "fmt" ? "format" : "lint";
  const result = (status, code, error) => {
    const value = {
      schema_version: "1.0.0",
      command: name,
      mode,
      status,
      child_exit_code: code,
    };
    if (error) value.error = error;
    if (json) process.stdout.write(JSON.stringify(value) + "\n");
  };
  const startupFailure = () => {
    const message = `Could not resolve or start the local Bun ${name === "format" ? "formatter" : "linter"}.`;
    const recovery = `${setup}, then retry node scripts/${name}.mjs${name === "format" ? (mode === "write" ? " --write" : " --check") : ""}`;
    if (json)
      result("failed", null, { stage: "local Bun startup", message, recovery });
    else process.stderr.write(`${message}\nTry: ${recovery}\n`);
    process.exitCode = 3;
  };
  let child;
  try {
    const { executable } = resolveLocalBun();
    child = spawn(executable, [command, "--no-script", ...args], {
      cwd: repositoryRoot,
      stdio: json ? ["inherit", "pipe", "inherit"] : "inherit",
      windowsHide: true,
    });
  } catch {
    startupFailure();
    return;
  }
  if (json) child.stdout.on("data", (chunk) => process.stderr.write(chunk));
  let settled = false;
  child.once("error", () => {
    if (settled) return;
    settled = true;
    startupFailure();
  });
  child.once("close", (code, signal) => {
    if (settled) return;
    settled = true;
    if (code === null && signal === null) {
      startupFailure();
      return;
    }
    const exitCode = code ?? 128 + (constants.signals[signal] ?? 1);
    result(exitCode === 0 ? "passed" : "failed", code);
    process.exitCode = exitCode;
  });
}
