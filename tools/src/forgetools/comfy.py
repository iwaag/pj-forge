"""ComfyUI jobs that survive the end of a process: submit once, inspect, collect once.

A job record (JSON, normally `jobs/<name>.json` in the run folder) is written
*before* the job is queued, with a prompt id chosen here and sent to ComfyUI.
So an interruption at any point leaves a record that names the job:

- `submit` refuses a record that already names a job ComfyUI knows, or has
  collected; a record left `submitting` is checked on the server and queued
  only if ComfyUI never received it — with the same id;
- `status` asks ComfyUI where the job is (queued, running, finished, failed,
  unknown) without changing anything;
- `collect` downloads the finished outputs, records their hashes, and is a
  no-op once they are recorded and still on disk.

Nothing here waits unboundedly: `collect --wait N` polls at most N seconds.

Presets configure a workflow export kept in the workspace's
`comfy/<preset>.json` of the project workspace (exports name model files, which are this
host's facts). Extracted from agforge `src/agforge/comfy_video.py`,
`comfy_music.py`, `comfy_async.py` at `26dc1df`, and from mediagen-localize
`flux2_scenery/generate.py` at `31c0ba1` (the FLUX.2 node settings).
"""

from __future__ import annotations

import copy
import os
import hashlib
import json
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests

from .local import LocalError, load_env, local_dir, require
from .storage import sha256_of

SCHEMA = "forge.comfy-job.v1"
MAX_SEED = 2**53 - 1


# ---------------------------------------------------------------- presets

def _only(graph: dict, class_type: str) -> dict:
    nodes = [node for node in graph.values() if isinstance(node, dict) and node.get("class_type") == class_type]
    if len(nodes) != 1:
        raise LocalError(f"the workflow must hold exactly one {class_type} node, found {len(nodes)}")
    return nodes[0]


def _all(graph: dict, class_type: str) -> list[dict]:
    return [node for node in graph.values() if isinstance(node, dict) and node.get("class_type") == class_type]


def _flux2_scenery(graph: dict, prompt: str, options: dict) -> dict:
    width, height = options.get("width") or 1344, options.get("height") or 768
    seed = options.get("seed") if options.get("seed") is not None else random.randint(0, MAX_SEED)
    steps, guidance = options.get("steps") or 8, options.get("guidance") or 4.0
    _only(graph, "CLIPTextEncode")["inputs"]["text"] = prompt
    _only(graph, "RandomNoise")["inputs"]["noise_seed"] = seed
    _only(graph, "FluxGuidance")["inputs"]["guidance"] = guidance
    for class_type in ("EmptyFlux2LatentImage", "Flux2Scheduler"):
        node = _only(graph, class_type)
        node["inputs"]["width"], node["inputs"]["height"] = width, height
    _only(graph, "PrimitiveBoolean")["inputs"]["value"] = True  # "Enable Turbo LoRA"
    switch = graph[_only(graph, "Flux2Scheduler")["inputs"]["steps"][0]]
    graph[switch["inputs"]["on_true"][0]]["inputs"]["value"] = steps
    return {"width": width, "height": height, "seed": seed, "steps": steps, "guidance": guidance,
            "unet": _only(graph, "UNETLoader")["inputs"].get("unet_name"),
            "lora": _only(graph, "LoraLoaderModelOnly")["inputs"].get("lora_name")}


def _video(graph: dict, prompt: str, options: dict) -> dict:
    _only(graph, "MiniMaxH3ImageToVideo")["inputs"]["prompt"] = prompt
    seed = options.get("seed") if options.get("seed") is not None else random.randint(0, MAX_SEED)
    for node in _all(graph, "RandomNoise"):
        node["inputs"]["noise_seed"] = seed
    return {"seed": seed}


def _music(graph: dict, prompt: str, options: dict) -> dict:
    seed = options.get("seed") if options.get("seed") is not None else random.randint(0, MAX_SEED)
    node = _only(graph, "TextEncodeAceStepAudio1.5")
    node["inputs"]["tags"], node["inputs"]["seed"] = prompt, seed
    for sampler in _all(graph, "KSampler"):
        sampler["inputs"]["seed"] = seed
    return {"seed": seed}


PRESETS = {
    "flux2-scenery": (_flux2_scenery, "FLUX.2 [dev] + Turbo LoRA text-to-image, wide scenery (default 1344x768, ~40 s warm)"),
    "video": (_video, "MiniMax H3 text-to-video, one 5-second clip with sound (minutes; needs most of the GPU)"),
    "music": (_music, "ACE-Step 1.5 text-to-music, one track (tens of seconds to minutes)"),
}


def preset_file(name: str) -> Path:
    return local_dir() / "comfy" / f"{name}.json"


def presets() -> list[dict]:
    return [{"preset": name, "about": about, "workflow_present": preset_file(name).is_file()}
            for name, (_, about) in PRESETS.items()]


def build(preset: str | None, prompt: str | None, options: dict, workflow: Path | None) -> tuple[dict, dict]:
    """(API graph, parameters) for a preset, or a ready graph given with --workflow."""
    if workflow is not None:
        graph = json.loads(workflow.read_text(encoding="utf-8"))
        return graph, {"workflow_file": workflow.name}
    if preset not in PRESETS:
        raise LocalError(f"unknown preset {preset!r}; `forge job presets` lists them")
    if not prompt or not prompt.strip():
        raise LocalError("--prompt is required with a preset")
    path = preset_file(preset)
    if not path.is_file():
        raise LocalError(f"the workspace has no comfy/{preset}.json (export the workflow in API format)")
    graph = copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))
    parameters = PRESETS[preset][0](graph, prompt, options)
    return graph, {"prompt": prompt, **parameters}


# ---------------------------------------------------------------- server

def base_url() -> str:
    (url,) = require(load_env(), "FORGE_COMFYUI_URL")
    return url.rstrip("/")


def _history(base: str, prompt_id: str) -> dict | None:
    response = requests.get(f"{base}/history/{prompt_id}", timeout=30)
    response.raise_for_status()
    return (response.json() or {}).get(prompt_id)


def _queue_position(base: str, prompt_id: str) -> str | None:
    response = requests.get(f"{base}/queue", timeout=30)
    response.raise_for_status()
    queue = response.json() or {}
    for state, key in (("running", "queue_running"), ("queued", "queue_pending")):
        for item in queue.get(key) or []:
            if len(item) > 1 and item[1] == prompt_id:
                return state
    return None


def server_state(base: str, prompt_id: str) -> dict:
    """{state: queued|running|finished|failed|unknown, ...} as ComfyUI sees the job now."""
    entry = _history(base, prompt_id)
    if entry:
        status = entry.get("status") or {}
        if str(status.get("status_str") or "").lower() == "error":
            errors = [message[1] for message in status.get("messages", []) if message and message[0] == "execution_error"]
            return {"state": "failed", "error": errors[0] if errors else status}
        return {"state": "finished", "outputs": output_references(entry)}
    position = _queue_position(base, prompt_id)
    return {"state": position or "unknown"}


def output_references(entry: dict) -> list[dict]:
    references = []
    for node_output in (entry.get("outputs") or {}).values():
        if isinstance(node_output, dict):
            for value in node_output.values():
                if isinstance(value, list):
                    references.extend(item for item in value if isinstance(item, dict) and item.get("filename"))
    return [ref for ref in references if ref.get("type", "output") == "output"] or references


def free_memory(base: str) -> bool:
    """Unload idle models before a large job; skipped when anything is queued (a shared GPU)."""
    try:
        queue = requests.get(f"{base}/queue", timeout=15).json()
        if queue.get("queue_running") or queue.get("queue_pending"):
            return False
        requests.post(f"{base}/free", json={"unload_models": True, "free_memory": True}, timeout=60)
    except (requests.RequestException, ValueError):
        return False
    return True


# ---------------------------------------------------------------- records

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def read(path: Path) -> dict:
    if not path.is_file():
        raise LocalError(f"no job record at {path}")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema") != SCHEMA:
        raise LocalError(f"{path} is not a {SCHEMA} record")
    return record


def _post(base: str, graph: dict, prompt_id: str) -> str:
    response = requests.post(f"{base}/prompt", json={"prompt": graph, "prompt_id": prompt_id,
                                                     "client_id": "forge-tools"}, timeout=60)
    if response.status_code >= 400:
        raise LocalError(f"ComfyUI refused the workflow (HTTP {response.status_code}): {response.text[:400]}")
    return str(response.json().get("prompt_id") or "")


def submit(record_path: Path, preset: str | None, prompt: str | None, options: dict,
           workflow: Path | None = None, free: bool = False) -> dict:
    base = base_url()
    if record_path.exists():
        record = read(record_path)
        if record["state"] != "submitting":
            raise LocalError(f"{record_path} already names job {record['prompt_id']} ({record['state']}); "
                             "use `forge job status` / `forge job collect`, or another --record for a new job")
        known = server_state(base, record["prompt_id"])
        if known["state"] != "unknown":
            record.update(state="submitted", submitted_at=record.get("submitted_at") or _now())
            record.setdefault("notes", []).append(f"{_now()} found on the server ({known['state']}); not queued again")
            _write(record_path, record)
            return record
        graph = json.loads(json.dumps(record["graph"]))
    else:
        graph, parameters = build(preset, prompt, options, workflow)
        record = {"schema": SCHEMA, "preset": preset or "custom", "parameters": parameters,
                  "graph_sha256": hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest(),
                  "prompt_id": str(uuid.uuid4()), "state": "submitting", "created_at": _now(),
                  "submitted_at": None, "outputs": [], "collected_at": None, "graph": graph}
        _write(record_path, record)
    if free:
        free_memory(base)
    answered = _post(base, graph, record["prompt_id"])
    if answered and answered != record["prompt_id"]:
        record.setdefault("notes", []).append(
            f"{_now()} the server ignored the chosen id {record['prompt_id']} and answered {answered}")
        record["prompt_id"] = answered
    record.update(state="submitted", submitted_at=_now())
    _write(record_path, record)
    return record


def status(record_path: Path) -> dict:
    record = read(record_path)
    summary = {k: record.get(k) for k in ("preset", "prompt_id", "state", "submitted_at", "collected_at")}
    summary["outputs_recorded"] = len(record.get("outputs") or [])
    summary["server"] = server_state(base_url(), record["prompt_id"])
    return summary


def collect(record_path: Path, into: Path, wait_seconds: int = 0, poll: float = 5.0) -> dict:
    record = read(record_path)
    if record["state"] == "collected":
        intact = all(path.is_file() and sha256_of(path) == item["sha256"]
                     for path, item in zip(_paths(record_path, record), record["outputs"]))
        if intact:
            return {"collected": False, "reason": "already collected; nothing downloaded",
                    "outputs": record["outputs"]}
        # recorded but missing or changed on disk: fetch the same job's outputs again
    if record["state"] == "submitting":
        raise LocalError("the record was never confirmed as queued: run `forge job submit` with the same --record "
                         "(it checks the server and queues only if ComfyUI never received it)")
    base = base_url()
    deadline = time.monotonic() + max(0, wait_seconds)
    while True:
        known = server_state(base, record["prompt_id"])
        if known["state"] == "failed":
            record.setdefault("notes", []).append(f"{_now()} failed on the server: {json.dumps(known['error'])[:400]}")
            record["state"] = "failed"
            _write(record_path, record)
            raise LocalError(f"job {record['prompt_id']} failed: {json.dumps(known['error'])[:400]}")
        if known["state"] == "finished":
            break
        if time.monotonic() >= deadline:
            return {"collected": False, "reason": f"job is {known['state']}; nothing downloaded",
                    "server": known}
        time.sleep(poll)
    into.mkdir(parents=True, exist_ok=True)
    outputs = []
    for reference in known["outputs"]:
        query = urlencode({"filename": reference["filename"], "subfolder": reference.get("subfolder", ""),
                           "type": reference.get("type", "output")})
        download = requests.get(f"{base}/view?{query}", timeout=300)
        download.raise_for_status()
        target = into / Path(reference["filename"]).name
        target.write_bytes(download.content)
        outputs.append({"file": _relative(target, record_path), "sha256": sha256_of(target),
                        "bytes": target.stat().st_size, "server_file": reference["filename"]})
    record.update(state="collected", outputs=outputs, collected_at=_now())
    _write(record_path, record)
    return {"collected": True, "outputs": outputs}


def _relative(path: Path, record_path: Path) -> str:
    # records are published with the run: never an absolute path
    return Path(os.path.relpath(path.resolve(), record_path.resolve().parent)).as_posix()


def _paths(record_path: Path, record: dict) -> list[Path]:
    paths = []
    for item in record.get("outputs") or []:
        path = Path(item["file"])
        paths.append(path if path.is_absolute() else record_path.parent / path)
    return paths
