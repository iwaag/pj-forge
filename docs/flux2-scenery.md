# The flux2-scenery route

FLUX.2 [dev] text-to-image with the Turbo LoRA, through ComfyUI, built for wide scenery
(default 1344×768). `tools/forge job submit flux2-scenery …` loads the workflow — the settings folder's
`comfy/flux2-scenery.json` if there is one, otherwise the bundled default — edits a few nodes
in memory and queues it.

## The workflow

`tools/src/forgetools/workflows/flux2-scenery.json` is the API-format export of ComfyUI's template
`image_flux2_text_to_image` (Comfy-Org/workflow_templates, MIT), unchanged (sha256
`c720a6d7c114cc84ccd4d0b3d70a5edb2b8677fed25993b166d2a683e20bd98b`). The tool never edits the
file; it finds nodes by class type, so a re-export from a newer template with the same node
classes keeps working, and a graph with two nodes of one of these classes is refused.

| Node (class type) | Field | Set to |
| --- | --- | --- |
| `CLIPTextEncode` | `text` | the prompt |
| `RandomNoise` | `noise_seed` | `--seed`, or a random seed that is recorded |
| `FluxGuidance` | `guidance` | `--guidance` (4) |
| `EmptyFlux2LatentImage`, `Flux2Scheduler` | `width`, `height` | `--width/--height` (1344×768) |
| `PrimitiveBoolean` ("Enable Turbo LoRA") | `value` | `true` (the template has `false`) |
| the `PrimitiveInt` on the true branch of the `ComfySwitchNode` feeding `Flux2Scheduler.steps` | `value` | `--steps` (8) |

Everything else stays as exported: sampler `euler`, LoRA strength 1, `SaveImage` prefix
`Flux2_dev`. The 20-step branch without the LoRA exists in the graph but is not reachable from
the command line. These settings (Turbo on, 1344×768, 8 steps, guidance 4) are the ones found
in the PNG metadata of two reference pictures the workflow was first used for; the template
differs from them only in the Turbo switch and the size.

## Models

Not distributed here. Links as given by the template (checked 2026-11-13); place them in the
ComfyUI folders named:

| ComfyUI folder | File | Size | Source | Licence (as stated at the source, 2026-11-13) |
| --- | --- | --- | --- | --- |
| `models/diffusion_models/` | `flux2_dev_fp8mixed.safetensors` | 33.02 GB | [Comfy-Org/flux2-dev](https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/diffusion_models/flux2_dev_fp8mixed.safetensors) | FLUX [dev] Non-Commercial License (black-forest-labs/FLUX.2-dev) |
| `models/text_encoders/` | `mistral_3_small_flux2_bf16.safetensors` | 33.14 GB | [Comfy-Org/flux2-dev](https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/text_encoders/mistral_3_small_flux2_bf16.safetensors) | check at the source |
| `models/loras/` | `Flux_2-Turbo-LoRA_comfyui.safetensors` | 2.57 GB | [ByteZSzn/Flux.2-Turbo-ComfyUI](https://huggingface.co/ByteZSzn/Flux.2-Turbo-ComfyUI/resolve/main/Flux_2-Turbo-LoRA_comfyui.safetensors) | none stated on the model page |
| `models/vae/` | `full_encoder_small_decoder.safetensors` | 238 MB | [black-forest-labs/FLUX.2-small-decoder](https://huggingface.co/black-forest-labs/FLUX.2-small-decoder/resolve/main/full_encoder_small_decoder.safetensors) | Apache-2.0 |

The file names must match the graph (or put your own export in the settings folder). The job record keeps
the model and LoRA file names, not their hashes.

## Timing (one server, see Evidence)

- About 40 s per 1344×768 picture with the models loaded (42.8 s and 38.4 s wall, 2026-09-23).
- About 4 minutes when ComfyUI loads them first (3 min 53 s, 2026-10-14; a job of 2026-11-02
  queued 17:27:00 and collected 17:30:51). Use `collect --wait 400` or more for a first job.

## Limits and failure modes

- Text-to-image only: no reference image, inpainting or image-to-image in this graph.
- **No negative prompt.** The graph uses `BasicGuider` + `FluxGuidance`, which have no negative
  input. Describe what you want. Observed once: a prompt for a meadow "seen from a field
  mouse's low height … no animals" produced a mouse in the foreground; removing the animal
  from the description ("extremely low ground-level camera angle … empty landscape") and a new
  seed gave a clean picture. Check each picture; re-roll with a new seed when needed.
- No control of text inside the picture or of exact composition.
- One picture per job (batch size 1).
- A shared GPU: a job may wait behind other work, or fail out of memory. `status` says where
  it is; retry later rather than in a loop. `--free` unloads idle models only when nothing is
  queued.
- A ComfyUI restart forgets queued jobs: `status` then says `unknown`, and the record must be
  submitted again under a new `--record` (the old one names a job the server no longer has).
  This follows from the code; it was not observed.
- Same seed, settings and server are expected to give the same picture; this was not
  measured across servers or versions.

## Evidence

All on the author's LAN (ComfyUI on one Quadro RTX 8000, 48 GB); not an independent reproduction.

- 2026-09-23: two 1344×768 forest pictures (42.8 s, 38.4 s), the first one looked at: a
  coherent low-angle forest without visible artefacts; colour somewhat teal-orange.
- 2026-10-14: through these tools; prompt id kept by the server, second submit refused, second
  collect a no-op; a run killed between submit and collect recovered with one `collect`.
- 2026-10-14 and 2026-11-02: pictures for two internal projects (title background, concept
  art), 1344×768, 8 steps, guidance 4.

## Where this knowledge comes from

The node settings, model list, timing and limits above restate notes of the author's private
media-generation knowledge base (not published; no public link exists). The failure modes come
from forge's private run records. This page is the self-contained public form of that
knowledge as of its revision date.
