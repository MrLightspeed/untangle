"""Resolve the repository's installed JavaScript runtimes for subprocess tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
_LOCAL_BUN_PROBE = (
    'import { resolveLocalBun } from "./scripts/local-bun.mjs"; '
    "process.stdout.write(JSON.stringify(resolveLocalBun()));"
)
_RUNTIME_PROBE = (
    "process.stdout.write(JSON.stringify({"
    'kind: process.versions.bun ? "Bun" : "Node", '
    "executable: process.execPath"
    "}));"
)


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _run(
    command: list[str], *, cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=_environment(),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def local_bun_info(
    root: Path = ROOT, node: str | None = NODE
) -> dict[str, str] | None:
    """Return the exact root-local Bun binary; never search PATH for Bun."""
    root = root.resolve()
    package_json = root / "node_modules/bun/package.json"
    if not package_json.is_file():
        return None
    if node is None:
        raise RuntimeError("Node is required to resolve the local Bun package.")

    helper = root / "scripts/local-bun.mjs"
    if not helper.is_file():
        raise RuntimeError("The local Bun resolver is missing.")

    completed = _run(
        [node, "--input-type=module", "-e", _LOCAL_BUN_PROBE],
        cwd=root,
    )
    if completed.returncode != 0:
        raise RuntimeError("The installed local Bun package could not be resolved.")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("The local Bun resolver returned invalid metadata.") from error
    if not isinstance(value, dict) or not all(
        isinstance(value.get(field), str)
        for field in ("executable", "packageName", "packageVersion")
    ):
        raise RuntimeError("The local Bun resolver returned incomplete metadata.")
    if not Path(value["executable"]).is_file():
        raise RuntimeError("The resolved local Bun executable is missing.")
    return value


def _runtime_identity(executable: str, root: Path) -> tuple[str, str]:
    completed = _run([executable, "-e", _RUNTIME_PROBE], cwd=root)
    if completed.returncode != 0:
        raise RuntimeError("A discovered JavaScript runtime failed its probe.")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("A discovered JavaScript runtime returned invalid metadata.") from error
    kind = value.get("kind")
    actual_executable = value.get("executable")
    if kind not in ("Node", "Bun") or not isinstance(actual_executable, str):
        raise RuntimeError("A discovered JavaScript runtime returned incomplete metadata.")
    identity = os.path.normcase(os.path.realpath(actual_executable))
    return kind, identity


def runtime_commands(root: Path = ROOT) -> list[tuple[str, str]]:
    """Return Node and the exact local Bun binary, de-duplicated by runtime."""
    root = root.resolve()
    commands: list[tuple[str, str]] = []
    identities: set[str] = set()

    if NODE:
        kind, identity = _runtime_identity(NODE, root)
        commands.append((kind, NODE))
        identities.add(identity)

    bun = local_bun_info(root)
    if bun:
        executable = bun["executable"]
        kind, identity = _runtime_identity(executable, root)
        if kind != "Bun":
            raise RuntimeError("The local platform package did not start Bun.")
        if identity not in identities:
            commands.append(("Bun", executable))
            identities.add(identity)

    return commands
