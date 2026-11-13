"""Images: SwarmUI text-to-image and image-to-image, and plain transforms.

Generation writes the file where it is told and prints one JSON line with the
conditions that made it (model, size, steps, cfg scale, seed, the reference
image's hash). Delivery is a separate step (`forge asset put`).

Extracted from agforge `src/agforge/generate.py` and `transform.py` at
`26dc1df`; the upload half is in `storage.py`.
"""

from __future__ import annotations

import base64
import mimetypes
import random
import re
from pathlib import Path

import requests

from .local import LocalError, load_env, require
from .storage import sha256_of

DEFAULTS = {"width": 1024, "height": 1024, "steps": 30, "cfgscale": 7}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "image"


def generate(prompt: str, out: Path, *, model: str | None = None, width: int | None = None,
             height: int | None = None, steps: int | None = None, cfgscale: float | None = None,
             seed: int | None = None, negative: str | None = None, init_image: Path | None = None,
             init_creativity: float = 0.6, name: str | None = None) -> dict:
    if not prompt.strip():
        raise LocalError("prompt is empty")
    env = load_env()
    (base,) = require(env, "FORGE_SWARMUI_URL")
    base = base.rstrip("/")
    params = {
        "model": model or env.get("FORGE_SWARMUI_MODEL"),
        "width": width or DEFAULTS["width"], "height": height or DEFAULTS["height"],
        "steps": steps or DEFAULTS["steps"], "cfgscale": cfgscale if cfgscale is not None else DEFAULTS["cfgscale"],
        "seed": seed if seed is not None else random.randint(1, 2**31 - 1),
    }
    if not params["model"]:
        raise LocalError("no model: pass --model or set FORGE_SWARMUI_MODEL in forge.env")
    payload: dict[str, object] = {"prompt": prompt, "images": 1, **params}
    if negative:
        payload["negativeprompt"] = negative
    conditions: dict[str, object] = {"route": "swarmui", "prompt": prompt, **params}
    if negative:
        conditions["negative"] = negative
    if init_image is not None:
        if not 0.0 <= init_creativity <= 1.0:
            raise LocalError("--init-creativity is a fraction between 0 and 1")
        if not init_image.is_file():
            raise LocalError(f"cannot read --init-image {init_image}")
        kind = mimetypes.guess_type(init_image.name)[0] or "image/png"
        encoded = base64.b64encode(init_image.read_bytes()).decode("ascii")
        payload["initimage"] = f"data:{kind};base64,{encoded}"
        payload["initimagecreativity"] = init_creativity
        conditions.update({"init_image": init_image.name, "init_image_sha256": sha256_of(init_image),
                           "init_creativity": init_creativity})

    session = requests.post(f"{base}/API/GetNewSession", json={}, timeout=30)
    session.raise_for_status()
    payload["session_id"] = session.json()["session_id"]
    response = requests.post(f"{base}/API/GenerateText2Image", json=payload, timeout=600)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise LocalError(f"SwarmUI error: {data['error']}")
    images = data.get("images") or []
    if not images:
        raise LocalError(f"SwarmUI returned no image: {str(data)[:300]}")
    reference = images[0]
    if reference.startswith("data:"):
        raise LocalError("SwarmUI answered a data URL; disable base64 output there")
    url = reference if reference.startswith("http") else f"{base}/{reference}"
    download = requests.get(url, timeout=120)
    download.raise_for_status()

    out.mkdir(parents=True, exist_ok=True)
    suffix = Path(reference.split("?")[0]).suffix or ".png"
    path = out / f"{name or _slug(prompt)}-s{params['seed']}{suffix}"
    path.write_bytes(download.content)
    return {"path": str(path), "sha256": sha256_of(path), "conditions": conditions}


def transform(source: Path, out: Path, *, width: int | None = None, height: int | None = None,
              fmt: str | None = None) -> dict:
    """Resize (to fit, keeping the aspect ratio unless both sides are given) and/or convert."""
    from PIL import Image

    if not source.is_file():
        raise LocalError(f"not a file: {source}")
    with Image.open(source) as image:
        result = image.copy()
    if width and height:
        result = result.resize((width, height), Image.LANCZOS)
    elif width or height:
        ratio = (width / result.width) if width else (height / result.height)
        result = result.resize((max(1, round(result.width * ratio)), max(1, round(result.height * ratio))),
                               Image.LANCZOS)
    target_format = (fmt or out.suffix.lstrip(".") or "png").lower()
    if target_format in ("jpg", "jpeg") and result.mode in ("RGBA", "LA", "P"):
        result = result.convert("RGB")
    out.parent.mkdir(parents=True, exist_ok=True)
    result.save(out, format="JPEG" if target_format in ("jpg", "jpeg") else target_format.upper())
    return {"path": str(out), "sha256": sha256_of(out), "width": result.width, "height": result.height,
            "mode": result.mode, "from": source.name, "from_sha256": sha256_of(source)}
