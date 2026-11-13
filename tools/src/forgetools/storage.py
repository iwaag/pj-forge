"""Durable delivery: content-addressed objects in the forge bucket, and fresh links.

A presigned URL expires; the object behind it does not. A delivery is
therefore recorded by its object key and content hash, and a link is made
from the key whenever someone needs one (`forge asset url <key>`).

Keys are `forge/<sha256[:2]>/<sha256><suffix>`: the same bytes always get
the same key, so uploading a file again changes nothing and a record can be
checked against the bucket at any time.

Extracted from agforge `src/agforge/generate.py` (`s3_bucket`, `presign`,
`object_exists`) and `request_service.py` (`/api/resign`) at `26dc1df`.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .local import LocalError, load_env, require

CONTENT_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
    ".gif": "image/gif", ".svg": "image/svg+xml",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac", ".m4a": "audio/mp4",
    ".aiff": "audio/aiff", ".ogg": "audio/ogg",
    ".md": "text/markdown; charset=utf-8", ".txt": "text/plain; charset=utf-8",
    ".json": "application/json", ".zip": "application/zip", ".pdf": "application/pdf",
}
MAX_TTL_MINUTES = 7 * 24 * 60  # S3 signature limit
RECORD_SCHEMA = "forge.delivery.v1"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def key_for(digest: str, suffix: str) -> str:
    return f"forge/{digest[:2]}/{digest}{suffix.lower()}"


def content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def bucket(env: dict[str, str] | None = None):
    """`(client, bucket name)` from forge.env."""
    import boto3

    env = load_env() if env is None else env
    endpoint, name, access, secret = require(
        env, "FORGE_S3_ENDPOINT", "FORGE_S3_BUCKET", "FORGE_S3_ACCESS_KEY", "FORGE_S3_SECRET_KEY")
    if name == "nctl-outbox":
        raise LocalError("refusing to write to the nctl-outbox bucket")
    client = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access,
                          aws_secret_access_key=secret, region_name="us-east-1")
    return client, name


def exists(client, name: str, key: str) -> bool:
    try:
        client.head_object(Bucket=name, Key=key)
    except Exception:  # noqa: BLE001 - any failure to confirm is a "no"
        return False
    return True


def link(key: str, ttl_minutes: int = 60, client_bucket=None) -> str:
    """A fresh download URL for a key the bucket holds; refuses one it does not.

    Signing is pure arithmetic and succeeds for keys that were never uploaded,
    so the object is confirmed first.
    """
    if not 1 <= ttl_minutes <= MAX_TTL_MINUTES:
        raise LocalError(f"--ttl is 1 to {MAX_TTL_MINUTES} minutes")
    client, name = client_bucket or bucket()
    if not exists(client, name, key):
        raise LocalError(f"the bucket holds no object {key}")
    return client.generate_presigned_url("get_object", Params={"Bucket": name, "Key": key},
                                         ExpiresIn=ttl_minutes * 60)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_record(path: Path) -> dict:
    if not path.exists():
        return {"schema": RECORD_SCHEMA, "items": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != RECORD_SCHEMA or not isinstance(data.get("items"), list):
        raise LocalError(f"{path} is not a {RECORD_SCHEMA} record")
    return data


def put(files: list[Path], record: Path, conditions: dict | None = None, note: str | None = None,
        client_bucket=None) -> list[dict]:
    """Upload each file (unless the bucket already has its bytes) and record it.

    The record is a JSON file, normally `deliveries.json` in the run folder;
    paths in it are relative to the record's folder. A file whose hash is
    already in the record is not added twice.
    """
    client, name = client_bucket or bucket()
    data = read_record(record)
    known = {item["sha256"]: item for item in data["items"]}
    results = []
    for path in files:
        if not path.is_file():
            raise LocalError(f"not a file: {path}")
        digest = sha256_of(path)
        key = key_for(digest, path.suffix)
        uploaded = False
        if not exists(client, name, key):
            client.upload_file(str(path), name, key, ExtraArgs={"ContentType": content_type(path)})
            uploaded = True
        # records are published with the run: never an absolute path
        relative = Path(os.path.relpath(path.resolve(), record.resolve().parent)).as_posix()
        if digest in known:
            item = known[digest]
            results.append({**item, "uploaded": uploaded, "recorded": False})
            continue
        item = {"file": relative, "sha256": digest, "bytes": path.stat().st_size, "key": key,
                "bucket": name, "content_type": content_type(path), "recorded_at": _now()}
        if conditions:
            item["conditions"] = conditions
        if note:
            item["note"] = note
        data["items"].append(item)
        known[digest] = item
        results.append({**item, "uploaded": uploaded, "recorded": True})
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return results


def check(record: Path, client_bucket=None) -> list[dict]:
    """Each recorded item: is it in the bucket, and do its bytes still hash the same?"""
    client, name = client_bucket or bucket()
    rows = []
    for item in read_record(record)["items"]:
        row = {"file": item["file"], "key": item["key"], "in_bucket": False, "hash_matches": False}
        try:
            body = client.get_object(Bucket=item.get("bucket", name), Key=item["key"])["Body"].read()
            row["in_bucket"] = True
            row["hash_matches"] = hashlib.sha256(body).hexdigest() == item["sha256"]
        except Exception:  # noqa: BLE001 - reported per row
            pass
        rows.append(row)
    return rows
