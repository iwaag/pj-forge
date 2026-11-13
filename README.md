# forge tools — scripted FLUX.2 scenery through ComfyUI, with job records

A small command-line tool (`tools/forge`) for generating images on your own ComfyUI
server from a script or an AI agent. The documented route makes wide scenery pictures with
FLUX.2 [dev] and a Turbo LoRA (8 steps). Every job is written to a JSON record *before* it is
queued, so a process that is interrupted — killed, timed out, restarted — can find the same
job again: it is never queued twice and its outputs are never downloaded twice.

This repository is a selected, edited publication of the tools of *forge*, the media-asset
project of a private agent-development system (agdev). It is not a mirror of that project:
the private catalog, run histories and host settings are not included ([NOTICE.md](NOTICE.md)).

## What you need

| | |
| --- | --- |
| Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/) | the launcher runs `uv run --project tools forge` |
| A ComfyUI server reachable over HTTP | recent core: the graph uses `Flux2Scheduler`, `EmptyFlux2LatentImage`, `ComfySwitchNode`, `PrimitiveInt`, `PrimitiveBoolean` (checked with ComfyUI 0.35.0) |
| The four model files in that server | ≈ 69 GB in total; download links and folders in [docs/flux2-scenery.md](docs/flux2-scenery.md#models). FLUX.2 [dev] is under a **non-commercial** licence. |
| A GPU with enough memory | checked on one 48 GB card only; smaller cards were not tried |
| A settings folder, outside any Git checkout | `forge.env` and `comfy/flux2-scenery.json`, see below |

Not needed for this route: credentials, agdev, S3 storage, SwarmUI.

## Setup

```sh
git clone https://github.com/iwaag/pj-forge.git && cd pj-forge
mkdir -p ~/forge-settings/comfy
cp workflows/flux2-scenery.api.json ~/forge-settings/comfy/flux2-scenery.json
echo "FORGE_COMFYUI_URL=http://<comfyui-host>:8188" > ~/forge-settings/forge.env
export FORGE_LOCAL=~/forge-settings
tools/forge local          # which settings folder applies and what is configured (values never printed)
tools/forge job presets    # flux2-scenery should say "workflow_present": true
```

`tools/forge.env.example` lists every key the other commands read. The settings folder is
yours to place; `FORGE_LOCAL` names it. (Inside agdev the folder is found from the project
workspace instead; nothing else in the tools depends on agdev.)

## Make a picture

```sh
tools/forge job submit flux2-scenery --record jobs/forest.json --seed 7 \
  --prompt "Low-angle view from the forest floor through a dense ancient forest, mossy trunks, sunbeams through mist, ferns, cinematic wide scenery"
tools/forge job collect jobs/forest.json --wait 400     # bounded wait; downloads into jobs/outputs/
```

`submit` returns immediately with the prompt id. `collect --wait N` polls at most N seconds:
about 40 s with the models loaded, about 4 minutes when ComfyUI has to load them first.
Without `--wait` it only reports where the job is. After an interruption:

```sh
tools/forge job status jobs/forest.json    # queued | running | finished | failed | unknown
tools/forge job collect jobs/forest.json --wait 400
```

`submit` refuses a record that already names a job; a record left `submitting` by a crash is
checked against the server and queued only if ComfyUI never received it, with the same id.

Options: `--width/--height` (default 1344×768), `--seed` (random and recorded when omitted),
`--steps` (8), `--guidance` (4), `--free` (unload idle models first; skipped when the GPU has
queued work). Every command prints JSON on stdout and a one-line refusal on stderr.

## What a job leaves behind (provenance)

- The job record (`forge.comfy-job.v1`): preset, parameters (prompt, size, seed, steps,
  guidance, model and LoRA file names), the full API graph as submitted and its sha256, the
  prompt id, timestamps, and each output's file, sha256 and size.
- The PNG as ComfyUI wrote it, with its `prompt` text chunk (the graph). There is no
  `workflow` chunk: the graph is submitted in API format.
- Optional durable delivery: `forge asset put <file> --record deliveries.json` uploads to an
  S3-compatible bucket under a key derived from the content hash and records key and hash;
  `forge asset url` makes a fresh link, `forge asset check` re-verifies the bytes. Needs
  `FORGE_S3_*` in `forge.env`. Not exercised in the check below.

The making facts of a picture (model, seed, prompt, graph) are only trustworthy for a file
whose sha256 still matches the record; a cropped or recompressed copy is a derivative and
should name the hash it came from.

## Evidence and limits

What was observed, and where — not a guarantee for other servers:

| Date | Observed | Where |
| --- | --- | --- |
| 2026-09-23 | 1344×768 forest, 42.8 s wall with models already loaded | the author's LAN, ComfyUI on a 48 GB Quadro RTX 8000 |
| 2026-10-14 | the same route through these tools: the server kept the tool's prompt id; a second submit on the same record was refused; a second collect downloaded nothing; 3 min 53 s with models cold | same |
| 2026-10-14 | a process killed between submit and collect; the job kept running and was collected once on resume | same |
| 2026-11-13 | this repository's README example, run from the published files with a settings folder holding only `FORGE_COMFYUI_URL`: 4 min 2 s, second submit refused, second collect a no-op ([examples/forest](examples/forest/)) | same |

Not demonstrated: another person's installation, other GPUs, other ComfyUI versions,
picture quality beyond a few prompts. Known limits and failure modes are in
[docs/flux2-scenery.md](docs/flux2-scenery.md#limits-and-failure-modes) — notably, there is no
negative prompt, and naming something to avoid can make it appear.

## Other commands

`forge image generate/transform` (SwarmUI and Pillow), `forge speech say` (macOS `say` +
ffmpeg), `forge asset …` (S3), `forge sources`, and the `video`/`music` presets are included
because they share the package. They are not documented or checked in this publication; see
`tools/forge <command> --help`. The `video` and `music` presets also need workflow exports
that are not published here.

Tests (fakes, no server): `cd tools && uv run pytest -q`.

## Licence

CC0 1.0 for this repository's own content ([LICENSE](LICENSE)); the workflow file is MIT
(Comfy Org) — see [NOTICE.md](NOTICE.md). Model weights are not included and carry their own
licences.
