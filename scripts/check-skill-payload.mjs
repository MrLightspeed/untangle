import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import path from "node:path";

export const expectedSkillFiles = Object.freeze(
  [
    "LICENSE.txt",
    "SKILL.md",
    "agents/openai.yaml",
    "references/diagram-patterns.md",
    "references/map-contract.md",
    "references/refactoring-practice.md",
    "scripts/render_map.py",
  ].sort(),
);

function physicalFiles(skill) {
  const found = [];
  function visit(directory) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const file = path.join(directory, entry.name);
      const relative = path.relative(skill, file).split(path.sep).join("/");
      assert(
        !entry.isSymbolicLink(),
        `Symlink in installable skill: ${relative}`,
      );
      if (entry.isDirectory()) {
        visit(file);
      } else {
        assert(entry.isFile(), `Non-file in installable skill: ${relative}`);
        if (
          relative.split("/").includes("__pycache__") &&
          relative.endsWith(".pyc")
        ) {
          continue;
        }
        found.push(relative);
      }
    }
  }
  visit(skill);
  return found;
}

function compare(actual, source) {
  const unexpected = actual.filter(
    (file) => !expectedSkillFiles.includes(file),
  );
  const missing = expectedSkillFiles.filter((file) => !actual.includes(file));
  assert.equal(
    unexpected.length,
    0,
    `Unexpected files in installable skill (${source}): ${unexpected.join(", ")}`,
  );
  assert.equal(
    missing.length,
    0,
    `Missing files from installable skill (${source}): ${missing.join(", ")}`,
  );
}

export function checkSkillPayload(root) {
  const skill = path.join(root, "skills", "untangle");
  compare(physicalFiles(skill), "working tree");

  // Git also sees tracked files in ignored locations such as __pycache__.
  if (!existsSync(path.join(root, ".git"))) return;
  const listed = execFileSync(
    "git",
    [
      "ls-files",
      "--cached",
      "--others",
      "--exclude-standard",
      "-z",
      "--",
      "skills/untangle",
    ],
    { cwd: root, encoding: "utf8", windowsHide: true, timeout: 30_000 },
  )
    .split("\0")
    .filter(Boolean)
    .map((file) => file.slice("skills/untangle/".length));
  compare(listed, "Git index and untracked files");
}
