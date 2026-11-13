# Notices

## This repository

- Own content (tools, documentation): CC0 1.0 Universal ([LICENSE](LICENSE)), by iwaag.
- It is an edited publication of the private *forge* project. Its history starts here; the
  private development history is not exported, and the public history is not a mirror of it.
  Each public commit names the private source revision it was made from.
- The tools were extracted from [iwaag/agforge](https://github.com/iwaag/agforge) at
  `26dc1dfe9e3df50b6145a01715e43ff1efd472e3` (CC0 1.0): `generate.py`, `transform.py`,
  `comfy_video.py`, `comfy_music.py`, `comfy_async.py` and the `/api/resign` handler of
  `request_service.py`. Module docstrings name these.
- Module docstrings also name `mediagen-localize flux2_scenery/generate.py at 31c0ba1`, a
  script of the author's private knowledge base; it is not published. What the tools took from
  it (the FLUX.2 node settings) is described in [docs/flux2-scenery.md](docs/flux2-scenery.md).

## Third-party material

- `workflows/flux2-scenery.api.json`: API-format export of the template
  `image_flux2_text_to_image` from [Comfy-Org/workflow_templates](https://github.com/Comfy-Org/workflow_templates),
  MIT License, Copyright (c) 2023-present Comfy Org — full text in
  [workflows/LICENSE-workflow-templates](workflows/LICENSE-workflow-templates).
- Model weights are not included. Each has its own licence, listed with the download links
  in [docs/flux2-scenery.md](docs/flux2-scenery.md#models); FLUX.2 [dev] is non-commercial.
- Python dependencies (Pillow, boto3, requests, pytest) are installed by `uv` from PyPI under
  their own licences.
