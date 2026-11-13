"""The knowledge sources this host has checked out (`sources.toml` of the project workspace).

The catalog cites a source as `<name>@<revision>:<path>`. This module says
where each named source is and which revision it is at now, so a run can read
it directly and record what it read. It reads no content and indexes nothing.
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

from .local import LocalError, local_dir

FILE = "sources.toml"


def load() -> list[dict]:
    path = local_dir() / FILE
    if not path.is_file():
        raise LocalError(f"missing {FILE} in the project workspace folder (tools/sources.example.toml is the shape)")
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    sources = data.get("source") or []
    for source in sources:
        if not source.get("name") or not source.get("path"):
            raise LocalError(f"{FILE}: every [[source]] needs name and path")
    return sources


def state(source: dict) -> dict:
    path = Path(source["path"]).expanduser()
    row = {"name": source["name"], "kind": source.get("kind", ""), "path": str(path),
           "about": source.get("about", ""), "revision": None, "dirty": None, "present": path.exists()}
    if not path.exists():
        return row
    try:
        head = subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=20)
        if head.returncode == 0:
            row["revision"] = head.stdout.strip()
            status = subprocess.run(["git", "-C", str(path), "status", "--porcelain"],
                                    capture_output=True, text=True, timeout=20)
            row["dirty"] = len([line for line in status.stdout.splitlines() if line.strip()])
    except (OSError, subprocess.TimeoutExpired):
        pass
    return row


def find(name: str) -> dict:
    for source in load():
        if source["name"] == name:
            return source
    raise LocalError(f"no source named {name!r} in {FILE}")
