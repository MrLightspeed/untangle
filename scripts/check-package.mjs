import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const skill = path.join(root, "skills", "untangle");
const read = (file) => readFileSync(file, "utf8");
let parseDocument;
let parseJsonc;
let lintSync;
let readConfigSync;
let checkSkillPayload;
const excluded = new Set([
  ".git",
  "node_modules",
  "__pycache__",
  ".venv",
  "work",
  "agent_ergonomics_audit",
]);

function files(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (excluded.has(entry.name)) return [];
    const target = path.join(directory, entry.name);
    if (target === path.join(root, "docs")) return [];
    assert(
      !entry.isSymbolicLink(),
      `Unexpected symlink: ${path.relative(root, target)}`,
    );
    return entry.isDirectory() ? files(target) : [target];
  });
}

function yaml(text, label) {
  const document = parseDocument(text, { uniqueKeys: true });
  assert.equal(document.errors.length, 0, `Invalid YAML: ${label}`);
  return document.toJS();
}

const help = `Usage: node scripts/check-package.mjs [--json]
       node scripts/check-package.mjs --help

Validate the installable skill, repository package metadata, Markdown links, and Markdown style.

Options:
  -h, --help  Show this help without running checks.
  --json      Emit one versioned JSON result; diagnostics are included in that result.

Commands:
  node scripts/check-package.mjs [--json]
  npm run check:package
  bun run check:package

Exit codes:
  0  Checks passed.
  1  A package check failed.
  2  Invalid arguments; run node scripts/check-package.mjs --help.
`;

function parseArguments(args) {
  let json = false;
  let showHelp = false;
  for (const argument of args) {
    if (argument === "--json") json = true;
    else if (argument === "--help" || argument === "-h") showHelp = true;
    else return { error: argument };
  }
  return { json, showHelp };
}

function errorMessage(error) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    message
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .slice(0, 5)
      .join(" ")
      .replace(/\s+/g, " ")
      .slice(0, 320) || "an unexpected validation error occurred"
  );
}

async function runChecks() {
  let stage = "skill package boundary";
  try {
    stage = "contributor dependencies";
    const [yamlModule, jsoncModule, markdownlintModule, payloadModule] =
      await Promise.all([
        import("yaml"),
        import("jsonc-parser"),
        import("markdownlint/sync"),
        import("./check-skill-payload.mjs"),
      ]);
    parseDocument = yamlModule.parseDocument;
    parseJsonc = jsoncModule.parse;
    lintSync = markdownlintModule.lint;
    readConfigSync = markdownlintModule.readConfig;
    checkSkillPayload = payloadModule.checkSkillPayload;

    stage = "skill package boundary";
    checkSkillPayload(root);

    stage = "skill metadata and package manifests";
    const entrypoint = read(path.join(skill, "SKILL.md"));
    const frontmatter = entrypoint.match(/^---\n([\s\S]*?)\n---\n/);
    assert(frontmatter, "SKILL.md needs YAML frontmatter and LF line endings");
    const metadata = yaml(frontmatter[1], "SKILL.md frontmatter");
    const allowed = new Set([
      "name",
      "description",
      "license",
      "compatibility",
      "metadata",
      "allowed-tools",
    ]);
    for (const key of Object.keys(metadata)) {
      assert(allowed.has(key), `Unsupported skill metadata field: ${key}`);
    }
    assert.equal(metadata.name, "untangle");
    assert.equal(path.basename(skill), metadata.name);
    assert(
      typeof metadata.description === "string" &&
        metadata.description.trim().length > 0,
    );
    assert(
      metadata.description.length <= 1024,
      "Skill description exceeds 1,024 characters",
    );
    assert(
      entrypoint.trimEnd().split("\n").length < 500,
      "Keep SKILL.md under 500 lines",
    );
    assert.equal(metadata.license, "MIT");
    if (metadata.compatibility !== undefined) {
      assert(
        typeof metadata.compatibility === "string" &&
          metadata.compatibility.length > 0 &&
          metadata.compatibility.length <= 500,
      );
    }
    assert.equal(
      read(path.join(root, "LICENSE")),
      read(path.join(skill, "LICENSE.txt")),
      "Installed license must match repository license",
    );

    const ui = yaml(
      read(path.join(skill, "agents", "openai.yaml")),
      "openai.yaml",
    );
    assert.equal(ui.interface.display_name, "Untangle");
    assert(
      ui.interface.short_description.length >= 25 &&
        ui.interface.short_description.length <= 64,
    );
    assert(ui.interface.default_prompt.includes("$untangle"));
    const plugin = JSON.parse(read(path.join(root, "plugin.json")));
    const project = JSON.parse(read(path.join(root, "package.json")));
    const npmLock = JSON.parse(read(path.join(root, "package-lock.json")));
    const lockErrors = [];
    const bunLock = parseJsonc(read(path.join(root, "bun.lock")), lockErrors, {
      allowTrailingComma: true,
    });
    assert.equal(lockErrors.length, 0, "Invalid bun.lock JSONC");
    assert.deepEqual(
      bunLock.workspaces[""].devDependencies,
      project.devDependencies,
      "Update bun.lock after changing development dependencies",
    );
    assert.deepEqual(
      npmLock.packages[""].devDependencies,
      project.devDependencies,
      "Update package-lock.json after changing development dependencies",
    );
    assert.equal(npmLock.version, project.version);
    const bunPackages = [
      ...new Set(Object.values(bunLock.packages).map((entry) => entry[0])),
    ].sort();
    const npmPackages = [
      ...new Set(
        Object.entries(npmLock.packages)
          .filter(([location]) => location !== "")
          .map(
            ([location, entry]) =>
              `${location.split("node_modules/").at(-1)}@${entry.version}`,
          ),
      ),
    ].sort();
    assert.deepEqual(
      npmPackages,
      bunPackages,
      "Keep npm and Bun lockfiles on the same dependency versions",
    );
    assert.equal(plugin.name, "untangle");
    assert.equal(plugin.version, project.version);
    assert.equal(
      plugin.$schema,
      "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
    );
    assert(/^\d+\.\d+\.\d+$/.test(plugin.version));

    stage = "Markdown documents and local links";
    let markdownCount = 0;
    const markdownFiles = [];
    for (const file of files(root)) {
      const label = path.relative(root, file);
      if (/\.ya?ml$/.test(file)) yaml(read(file), label);
      if (/\.json$/.test(file)) JSON.parse(read(file));
      if (!file.endsWith(".md")) continue;
      markdownCount += 1;
      markdownFiles.push(file);
      const body = read(file)
        .replace(/^---\n[\s\S]*?\n---\n/, "")
        .replace(/^```[^\n]*\n[\s\S]*?^```\s*$/gm, "");
      for (const match of body.matchAll(/!?\[[^\]\n]*\]\(([^)\n]+)\)/g)) {
        const href = match[1].trim().replace(/^<|>$/g, "");
        if (/^(?:[a-z][a-z0-9+.-]*:|#)/i.test(href)) continue;
        const target = path.resolve(
          path.dirname(file),
          decodeURIComponent(href.split("#")[0]),
        );
        const relative = path.relative(root, target);
        assert(
          relative !== ".." &&
            !relative.startsWith(`..${path.sep}`) &&
            !path.isAbsolute(relative),
          `Link escapes package: ${label}`,
        );
        assert(
          existsSync(target),
          `Missing local Markdown link target in ${label}`,
        );
        if (file.startsWith(`${skill}${path.sep}`)) {
          const packageRelative = path.relative(skill, target);
          assert(
            packageRelative !== ".." &&
              !packageRelative.startsWith(`..${path.sep}`),
            `Installed skill link escapes its package: ${label}`,
          );
        }
      }
    }

    stage = "Markdown lint";
    const markdownResults = lintSync({
      files: markdownFiles,
      config: readConfigSync(path.join(root, ".markdownlint.json")),
    });
    const diagnostics = [];
    for (const [file, errors] of Object.entries(markdownResults)) {
      for (const error of errors) {
        diagnostics.push(
          `${path.relative(root, file)}:${error.lineNumber}: ${error.ruleNames.join(", ")} ${error.ruleDescription}`,
        );
      }
    }
    return { markdownCount, diagnostics };
  } catch (error) {
    const wrapped = new Error(errorMessage(error));
    wrapped.stage = stage;
    if (error && typeof error === "object" && "code" in error) {
      wrapped.code = error.code;
    }
    throw wrapped;
  }
}

function emitJson(result) {
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

async function main() {
  const args = parseArguments(process.argv.slice(2));
  if (args.showHelp) {
    process.stdout.write(help);
    return;
  }
  if ("error" in args) {
    process.stderr.write(
      `Unknown argument: ${JSON.stringify(args.error)}\nTry: node scripts/check-package.mjs --help\n`,
    );
    process.exitCode = 2;
    return;
  }

  try {
    const result = await runChecks();
    const failed = result.diagnostics.length > 0;
    if (args.json) {
      emitJson({
        schema_version: "1.0.0",
        command: "check-package",
        status: failed ? "failed" : "passed",
        markdown_documents_checked: result.markdownCount,
        markdown_failures: result.diagnostics.length,
        diagnostics: result.diagnostics,
      });
    } else if (failed) {
      for (const diagnostic of result.diagnostics) {
        process.stderr.write(`${diagnostic}\n`);
      }
      process.exitCode = 1;
    } else {
      process.stdout.write(
        `Package checks passed; ${result.markdownCount} Markdown documents checked.\n`,
      );
    }
    if (failed) process.exitCode = 1;
  } catch (error) {
    const stage = error.stage ?? "package validation";
    const message = errorMessage(error);
    const missingDependency = error.code === "ERR_MODULE_NOT_FOUND";
    const recovery = missingDependency
      ? "bun install --frozen-lockfile --ignore-scripts (or npm ci --ignore-scripts), then retry node scripts/check-package.mjs"
      : "node scripts/check-package.mjs --help";
    if (args.json) {
      emitJson({
        schema_version: "1.0.0",
        command: "check-package",
        status: "failed",
        error: {
          stage,
          message,
          recovery,
        },
      });
    } else {
      process.stderr.write(
        `Package check failed during ${stage}: ${message}\nTry: ${recovery}\n`,
      );
    }
    process.exitCode = 1;
  }
}

await main();
