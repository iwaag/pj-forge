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
| A settings folder, outside any Git checkout | `forge.env` with the server's URL, see below |

Not needed for this route: credentials, agdev, S3 storage, SwarmUI.

## Setup

```sh
git clone https://github.com/iwaag/pj-forge.git && cd pj-forge
mkdir -p ~/forge-settings
echo "FORGE_COMFYUI_URL=http://<comfyui-host>:8188" > ~/forge-settings/forge.env
export FORGE_LOCAL=~/forge-settings
tools/forge local          # which settings folder applies and what is configured (values never printed)
tools/forge job presets    # flux2-scenery: "workflow_present": true, "workflow": "bundled"
```

The workflow is bundled with the tools (`tools/src/forgetools/workflows/flux2-scenery.json`).
If your server names the model files differently, export your own graph in API format to
`<settings folder>/comfy/flux2-scenery.json`: it takes precedence, and `job presets` and each
job record (`parameters.workflow`) say which one was used.

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

## The other tools: what exists and what was checked

The package has more commands than the documented flux2 route. This table says what each
does and how far it was checked. "Checked" always means: run by the author, on the author's
own machines, on the dates given; none was reproduced by anyone else.

| Want | Command | Needs in `forge.env` / host | Checked | Limits |
| --- | --- | --- | --- | --- |
| Wide scenery image | `forge job submit flux2-scenery` | `FORGE_COMFYUI_URL` | yes, see above | documented above |
| Any image from a prompt, or a variant of a reference image | `forge image generate "<prompt>" --out DIR [--init-image F --init-creativity 0.6]` | a [SwarmUI](https://github.com/mcmonkeyprojects/SwarmUI) server: `FORGE_SWARMUI_URL`, and `FORGE_SWARMUI_MODEL` (or `--model`) naming a checkpoint it lists | once, 2026-10-14: a 768×768 text-to-image in about 25 s (SDXL checkpoint, 20 steps) and an image-to-image of it at creativity 0.5 that kept the composition and changed one colour. Not re-run since; a later partial probe (2026-10-18) of the author's SwarmUI found its API calls returning errors, so treat this route as unconfirmed for current SwarmUI versions | opaque output only (no transparency); no reliable text inside the picture; the output depends on your checkpoint |
| Resize or convert an image | `forge image transform F --out G [--width W] [--height H] [--format png\|jpeg\|webp]` | Pillow (installed by `uv`) | once, 2026-10-14: a 768×768 JPEG to a 256×256 PNG | plain resize/convert; for anything else use Pillow directly |
| A spoken line as a WAV | `forge speech say "<text>" --out line.wav [--voice NAME] [--rate 48000] [--pad 0.3]` | **macOS** (`say`) and `ffmpeg` on the path | format only, 2026-10-14: three Japanese lines, voice `Kyoko`, came out as 48 kHz mono WAV with silence at both ends. **No one has listened to them**, so how intelligible they are is not established | system voice, flat delivery, no acting or emotion control; only voices listed by `say -v '?'`; other languages untried |
| Music track, video clip | `forge job submit music` / `video` | `FORGE_COMFYUI_URL` and your own workflow export at `<settings folder>/comfy/music.json` / `video.json` (not published here) | no: used by an earlier version in September 2026, not run with these tools | no workflow is included, so these presets do nothing until you provide one |
| Short sound effects | not in this repository | — | — | the author handles these in a separate project; this tool does not make them |

Example (image, from a SwarmUI server configured in `forge.env`):

```sh
tools/forge image generate "a red apple on a wooden table, soft daylight" --out out/ --seed 42
tools/forge image transform out/*.png --out out/apple-256.png --width 256
tools/forge speech say "Hello. This is a test line." --out out/line.wav --voice Samantha   # macOS
```

Each prints JSON with the file path, its sha256 and the conditions used (model, seed, size…).
The voice name `Samantha` is only an example of a macOS voice; it was not tried here.

Other commands: `forge asset …` delivers files to an S3-compatible bucket and
re-verifies them (`FORGE_S3_*`; not exercised in the checks above), `forge sources` lists
knowledge folders of the author's setup and is of no use elsewhere. `tools/forge <command> --help`
shows every option.

Tests (fakes, no server): `cd tools && uv run pytest -q`.

## Licence

CC0 1.0 for this repository's own content ([LICENSE](LICENSE)); the bundled workflow file is MIT
(Comfy Org) — see [NOTICE.md](NOTICE.md). Model weights are not included and carry their own
licences.
