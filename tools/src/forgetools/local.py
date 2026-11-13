"""Where this host's forge settings are: the project workspace folder.

A project workspace is a local folder around the project's checkout
(`<workspace>/source/`); the settings are files beside the checkout, never in
Git. A run works in its own checkout, `<workspace>/.agdev/runs/<wf>/<run>/source/`,
and reads the settings of the project workspace it belongs to, found from its
location (or `$AGDEV_PROJECT_WORKSPACE`, which the executor sets);
`FORGE_LOCAL` names the folder explicitly instead.

Files read there (examples beside these tools: `forge.env.example`,
`sources.example.toml`):

- `forge.env` — KEY=VALUE lines: service endpoints and storage credentials;
- `sources.toml` — where the knowledge sources are checked out;
- `comfy/<preset>.json` — ComfyUI workflow exports the presets load;
- `localenv.md` — prose notes about this host, for people and agents.

Nothing here is printed by the tools except names and states.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = "forge.env"


class LocalError(SystemExit):
    """A missing or unreadable host setting, said in one line."""


def _copy_workspace(path: Path) -> Path | None:
    # <workspace>/.agdev/runs/<wf>/<run>/source/... -> <workspace>
    parts = path.parts
    for index in range(len(parts) - 2, 0, -1):
        if parts[index:index + 2] == (".agdev", "runs"):
            return Path(*parts[:index])
    return None


def _project_root(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        if (candidate / "project.yaml").is_file():
            return candidate
    return None


def local_dir(start: Path | None = None) -> Path:
    """The project workspace folder whose settings apply here."""
    explicit = os.environ.get("FORGE_LOCAL")
    if explicit:
        return Path(explicit).expanduser().resolve()
    origins = [Path.cwd() if start is None else start, Path(__file__).resolve()]
    for origin in origins:
        workspace = _copy_workspace(origin.resolve())
        if workspace is not None:
            return workspace
    project = os.environ.get("AGDEV_PROJECT_WORKSPACE")
    if project:
        return Path(project).expanduser().resolve()
    for origin in origins:
        root = _project_root(origin.resolve())
        if root is not None:
            # the checkout is <workspace>/source
            return root.parent
    raise LocalError("cannot tell which project workspace this is: run inside the project "
                     "(or a run's checkout of it), or set FORGE_LOCAL to the workspace folder")


def load_env(start: Path | None = None) -> dict[str, str]:
    """`forge.env` as a dict; environment variables of the same name win."""
    path = local_dir(start) / ENV_FILE
    if not path.is_file():
        raise LocalError(f"missing {ENV_FILE} in the project workspace folder "
                         "(tools/forge.env.example is the shape)")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    for key in list(values):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def require(env: dict[str, str], *keys: str) -> list[str]:
    missing = [key for key in keys if not env.get(key)]
    if missing:
        raise LocalError(f"missing in the workspace's {ENV_FILE}: {', '.join(missing)}")
    return [env[key] for key in keys]
