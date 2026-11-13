# Example: the README's forest job

Made on 2026-11-13 with this repository's candidate and the setup in the top-level README
(a settings folder holding only `FORGE_COMFYUI_URL` and the published workflow), against the
author's ComfyUI (0.35.0, one Quadro RTX 8000). Submitted 10:59:14Z, collected 11:03:16Z:
about 4 minutes, consistent with the models not being loaded yet.

- `forest.json` — the job record exactly as `forge job submit` / `collect` wrote it.
- `preview.jpg` — a 1024×585 JPEG made from the collected PNG with `sips`; a derivative, so the
  record's making facts apply to its parent, PNG sha256
  `d265012db92d85bcb05e946c832f976a4601c91bc1d7caa826b65437363d6d41` (1344×768, 2,007,051
  bytes, `prompt` text chunk present). The PNG itself is not included.

Same seed and settings on another server are expected, not shown, to give the same picture.
The picture was made with FLUX.2 [dev]; see its licence for how outputs may be used.
