"""Own disposable contributor fixtures under the repository's ignored work root."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
FIXTURE_NAME = re.compile(r"fx-[0-9a-f]{16}")
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)


def directory_identity(path: Path) -> list[int]:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or (
        getattr(info, "st_file_attributes", 0) & REPARSE_POINT
    ):
        raise RuntimeError(f"Expected an ordinary fixture directory: {path}")
    return [info.st_dev, info.st_ino]


def create_fixture(*, owner_pid: int | None = None) -> Path:
    WORK.mkdir(exist_ok=True)
    root_identity = directory_identity(WORK)
    name = f"fx-{uuid4().hex[:16]}"
    fixture = WORK / name
    record = WORK / f"{name}.json"
    record_stat = None
    created = False
    fixture_identity = None
    try:
        with record.open("x", encoding="utf-8") as stream:
            # Reserve the journal before creating anything that needs cleanup.
            record_stat = os.fstat(stream.fileno())
            fixture.mkdir()
            created = True
            fixture_identity = directory_identity(fixture)
            json.dump({
                "name": name,
                "owner_pid": owner_pid if owner_pid is not None else os.getpid(),
                "root_identity": root_identity,
                "fixture_identity": fixture_identity,
                "state": "active or interrupted",
            }, stream)
    except BaseException:
        if record_stat is not None:
            try:
                if directory_identity(WORK) != root_identity or not os.path.samestat(record.lstat(), record_stat):
                    raise RuntimeError("Fixture receipt ownership changed during setup")
                if created:
                    if directory_identity(fixture) != fixture_identity:
                        raise RuntimeError("Fixture directory ownership changed during setup")
                    fixture.rmdir()
                record.unlink()
            except (OSError, RuntimeError) as cleanup_error:
                raise RuntimeError(f"Fixture setup cleanup failed; inspect {fixture} and {record}") from cleanup_error
        raise
    return fixture


def clean_fixture(fixture: Path) -> None:
    if fixture.parent != WORK or not FIXTURE_NAME.fullmatch(fixture.name):
        raise RuntimeError(f"Fixture path is outside managed scratch: {fixture}")
    directory_identity(WORK)
    record = WORK / f"{fixture.name}.json"
    info = record.lstat()
    if not stat.S_ISREG(info.st_mode) or (
        getattr(info, "st_file_attributes", 0) & REPARSE_POINT
    ):
        raise RuntimeError(f"Fixture receipt is not an ordinary file: {record}")
    identity = json.loads(record.read_text(encoding="utf-8"))
    if (
        identity["name"] != fixture.name
        or identity["root_identity"] != directory_identity(WORK)
        or identity["fixture_identity"] != directory_identity(fixture)
    ):
        raise RuntimeError(f"Fixture identity changed, preserved for review: {fixture}")

    def remove_read_only_file(function, path, error):
        # Rollback tests intentionally preserve file permissions. Change only
        # an owned, ordinary file, as a hard link can share permissions.
        entry = Path(path)
        bits = entry.lstat()
        if (
            os.name != "nt"
            or not isinstance(error, PermissionError)
            or function is not os.unlink
            or not stat.S_ISREG(bits.st_mode)
            or bits.st_nlink != 1
            or getattr(bits, "st_file_attributes", 0) & REPARSE_POINT
            or not entry.is_relative_to(fixture)
        ):
            raise error
        entry.chmod(bits.st_mode | stat.S_IWRITE)
        function(path)

    try:
        # Python's tree removal unlinks symlinks and Windows junctions without
        # traversing them. The lstat checks above also reject a linked root.
        shutil.rmtree(fixture, onexc=remove_read_only_file)
        record.unlink()
    except OSError as error:
        raise RuntimeError(f"Fixture cleanup failed; inspect {fixture} and {record}") from error


class TemporaryFixture:
    """A fixture with the same context/cleanup interface used by unittest."""

    def __init__(self) -> None:
        self.path = create_fixture()
        self.name = str(self.path)
        self._clean = False

    def __enter__(self) -> str:
        return self.name

    def cleanup(self) -> None:
        if not self._clean:
            clean_fixture(self.path)
            self._clean = True

    def __exit__(self, *exc: object) -> None:
        self.cleanup()


if __name__ == "__main__":
    if sys.argv[1:] == ["create"]:
        print(create_fixture(owner_pid=os.getppid()))
    elif len(sys.argv) == 3 and sys.argv[1] == "clean":
        clean_fixture(Path(sys.argv[2]))
    else:
        raise SystemExit("Usage: fixture_lifecycle.py create | clean <recorded path>")
