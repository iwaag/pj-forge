"""forge — the project's media tools. `forge <command> --help` is the usage.

  forge local                       which workspace settings apply here, and what is configured
  forge sources                     the knowledge sources on this host: name, path, revision
  forge image generate "<prompt>"   one image through SwarmUI (text-to-image, or --init-image)
  forge image transform <file>      resize / convert an image
  forge speech say "<text>"         one WAV through macOS's `say` + ffmpeg (system TTS, not acting)
  forge asset put <file>…           durable delivery: upload by content hash, record key and hash
  forge asset url <key>             a fresh download link for a delivered object
  forge asset check <record>        are the recorded objects still there, byte for byte?
  forge job presets                 ComfyUI presets and whether this host has their workflow
  forge job submit|status|collect   a ComfyUI job with a saved record: submit once, collect once

Every command prints JSON on stdout (one object, or one line per row) and
explains a refusal on stderr with exit status 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import comfy, images, sources, speech, storage
from .local import LocalError, ENV_FILE, local_dir, load_env


def _print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=None))


def cmd_local(args):
    folder = local_dir()
    env_present = (folder / ENV_FILE).is_file()
    keys = sorted(load_env()) if env_present else []
    _print({"local": str(folder), "forge.env": env_present, "configured": keys,
            "sources.toml": (folder / sources.FILE).is_file(),
            "comfy_presets": [p["preset"] for p in comfy.presets() if p["workflow_present"]],
            "localenv.md": (folder / "localenv.md").is_file()})


def cmd_sources(args):
    for source in sources.load():
        _print(sources.state(source))


def cmd_image_generate(args):
    _print(images.generate(args.prompt, args.out, model=args.model, width=args.width, height=args.height,
                           steps=args.steps, cfgscale=args.cfgscale, seed=args.seed, negative=args.negative,
                           init_image=args.init_image, init_creativity=args.init_creativity, name=args.name))


def cmd_image_transform(args):
    _print(images.transform(args.file, args.out, width=args.width, height=args.height, fmt=args.format))


def cmd_speech_say(args):
    _print(speech.synthesize(args.text, args.out, voice=args.voice, rate=args.rate, pad=args.pad))


def cmd_asset_put(args):
    conditions = None
    if args.conditions:
        text = Path(args.conditions).read_text(encoding="utf-8") if Path(args.conditions).is_file() else args.conditions
        conditions = json.loads(text)
        conditions = conditions.get("conditions", conditions)
    for row in storage.put(args.files, args.record, conditions=conditions, note=args.note):
        _print(row)


def cmd_asset_url(args):
    print(storage.link(args.key, args.ttl))


def cmd_asset_check(args):
    rows = storage.check(args.record)
    for row in rows:
        _print(row)
    if not all(row["in_bucket"] and row["hash_matches"] for row in rows):
        sys.exit(1)


def cmd_job_presets(args):
    for row in comfy.presets():
        _print(row)


def cmd_job_submit(args):
    options = {"seed": args.seed, "width": args.width, "height": args.height, "steps": args.steps,
               "guidance": args.guidance}
    record = comfy.submit(args.record, args.preset, args.prompt, options, workflow=args.workflow, free=args.free)
    _print({k: record[k] for k in ("preset", "prompt_id", "state", "submitted_at", "parameters")})


def cmd_job_status(args):
    _print(comfy.status(args.record))


def cmd_job_collect(args):
    _print(comfy.collect(args.record, args.into or args.record.parent / "outputs", wait_seconds=args.wait))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    local = commands.add_parser("local", help="which workspace settings apply here",
                                description="Print the project workspace folder these tools read "
                                            "(found from a run copy's location, or FORGE_LOCAL), and which "
                                            "settings it has. Values are never printed.")
    local.set_defaults(run=cmd_local)

    src = commands.add_parser("sources", help="knowledge sources: name, path, revision",
                              description="One JSON line per [[source]] in the workspace's sources.toml: where it is "
                                          "checked out, its git revision and how many uncommitted files it "
                                          "has. Read the files directly; cite them as <name>@<revision>:<path>.")
    src.set_defaults(run=cmd_sources)

    image = commands.add_parser("image", help="images").add_subparsers(dest="action", required=True)
    gen = image.add_parser("generate", help="one image through SwarmUI",
                           description="Generate one image through SwarmUI into --out and print its path, "
                                       "hash and the conditions that made it (model, size, steps, cfg scale, "
                                       "seed, reference image). Seconds per image. --init-image starts from "
                                       "a reference (image-to-image): its composition, framing and palette "
                                       "steer the result and the prompt says what changes.")
    gen.add_argument("prompt")
    gen.add_argument("--out", type=Path, required=True, help="directory to write the image into")
    gen.add_argument("--name", help="file name stem (default: from the prompt)")
    gen.add_argument("--model", help="SwarmUI model name (default: FORGE_SWARMUI_MODEL)")
    gen.add_argument("--width", type=int)
    gen.add_argument("--height", type=int)
    gen.add_argument("--steps", type=int)
    gen.add_argument("--cfgscale", type=float)
    gen.add_argument("--seed", type=int, help="default: random, printed in the conditions")
    gen.add_argument("--negative", help="negative prompt")
    gen.add_argument("--init-image", type=Path, metavar="PATH")
    gen.add_argument("--init-creativity", type=float, default=0.6, metavar="FRACTION",
                     help="0 keeps the reference, 1 ignores it (default 0.6)")
    gen.set_defaults(run=cmd_image_generate)
    tr = image.add_parser("transform", help="resize / convert",
                          description="Resize (fit one side keeping the aspect ratio, or both sides exactly) "
                                      "and/or convert by the output's extension. Pillow is also available for "
                                      "anything else: `uv run --with pillow python …`.")
    tr.add_argument("file", type=Path)
    tr.add_argument("--out", type=Path, required=True)
    tr.add_argument("--width", type=int)
    tr.add_argument("--height", type=int)
    tr.add_argument("--format", help="png, jpeg, webp … (default: from --out)")
    tr.set_defaults(run=cmd_image_transform)

    speech_cmd = commands.add_parser("speech", help="spoken voice lines").add_subparsers(dest="action", required=True)
    say = speech_cmd.add_parser("say", help="one WAV through macOS's `say` + ffmpeg",
                                description="System text-to-speech (macOS `say`) resampled and padded with "
                                            "ffmpeg into one mono WAV. Intelligible, flat prosody — not "
                                            "acting; 'calm, gentle' delivery is not controllable beyond "
                                            "voice choice and speaking rate. No model, service or paid API.")
    say.add_argument("text")
    say.add_argument("--out", type=Path, required=True, help="WAV file to write")
    say.add_argument("--voice", default=speech.DEFAULT_VOICE, help=f"a `say -v '?'` voice (default {speech.DEFAULT_VOICE}, Japanese female)")
    say.add_argument("--rate", type=int, default=speech.DEFAULT_RATE, metavar="HZ", help=f"default {speech.DEFAULT_RATE}")
    say.add_argument("--pad", type=float, default=speech.DEFAULT_PAD, metavar="SECONDS",
                     help=f"silence added at both start and end (default {speech.DEFAULT_PAD})")
    say.set_defaults(run=cmd_speech_say)

    asset = commands.add_parser("asset", help="durable delivery").add_subparsers(dest="action", required=True)
    put = asset.add_parser("put", help="upload by content hash and record key and hash",
                           description="Upload each file to the forge bucket under a key derived from its "
                                       "SHA-256 (the same bytes never upload twice) and add it to a delivery "
                                       "record (JSON, normally deliveries.json in the run folder). The key "
                                       "and hash are the durable delivery; a link is made from the key with "
                                       "`forge asset url`.")
    put.add_argument("files", nargs="+", type=Path)
    put.add_argument("--record", type=Path, required=True)
    put.add_argument("--conditions", help="JSON (or a file holding it) of how the files were made; the "
                                          "output of `forge image generate` is accepted as is")
    put.add_argument("--note", help="one line about these files")
    put.set_defaults(run=cmd_asset_put)
    url = asset.add_parser("url", help="a fresh download link for a key",
                           description="Print a presigned download URL for a key the bucket holds (refused "
                                       "for a key it does not). Links expire; keys do not.")
    url.add_argument("key")
    url.add_argument("--ttl", type=int, default=60, metavar="MINUTES", help="1 to 10080 (7 days); default 60")
    url.set_defaults(run=cmd_asset_url)
    chk = asset.add_parser("check", help="verify a delivery record against the bucket",
                           description="Download each recorded object and compare its hash. Exit 1 when any "
                                       "is missing or differs.")
    chk.add_argument("record", type=Path)
    chk.set_defaults(run=cmd_asset_check)

    job = commands.add_parser("job", help="ComfyUI jobs with saved records").add_subparsers(dest="action", required=True)
    pre = job.add_parser("presets", help="presets and whether this host has their workflow export")
    pre.set_defaults(run=cmd_job_presets)
    sub = job.add_parser("submit", help="queue one job, recorded before it is queued",
                         description="Write the job record (with the prompt id) first, then queue the job "
                                     "and return without waiting. A record that already names a job is "
                                     "refused; one left 'submitting' by an interruption is checked on the "
                                     "server and queued only if ComfyUI never received it. Collect with "
                                     "`forge job collect`.")
    sub.add_argument("preset", nargs="?", help="see `forge job presets`; omit with --workflow")
    sub.add_argument("--record", type=Path, required=True, help="job record to create, e.g. jobs/<name>.json")
    sub.add_argument("--prompt")
    sub.add_argument("--workflow", type=Path, help="a ready API-format graph instead of a preset")
    sub.add_argument("--seed", type=int)
    sub.add_argument("--width", type=int)
    sub.add_argument("--height", type=int)
    sub.add_argument("--steps", type=int)
    sub.add_argument("--guidance", type=float)
    sub.add_argument("--free", action="store_true", help="unload idle models first (skipped if the GPU is busy)")
    sub.set_defaults(run=cmd_job_submit)
    st = job.add_parser("status", help="where the recorded job is now",
                        description="Ask ComfyUI about the recorded job: queued, running, finished, failed, "
                                    "or unknown (never received, or lost by a restart). Changes nothing.")
    st.add_argument("record", type=Path)
    st.set_defaults(run=cmd_job_status)
    col = job.add_parser("collect", help="download a finished job's outputs once",
                         description="Download the finished job's outputs into --into (default: outputs/ "
                                     "beside the record) and record their hashes. Once recorded and intact "
                                     "on disk, collecting again downloads nothing. --wait N polls at most N "
                                     "seconds for an unfinished job; without it an unfinished job is "
                                     "reported and nothing is downloaded.")
    col.add_argument("record", type=Path)
    col.add_argument("--into", type=Path)
    col.add_argument("--wait", type=int, default=0, metavar="SECONDS")
    col.set_defaults(run=cmd_job_collect)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.run(args)
    except LocalError as error:
        print(f"forge: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
