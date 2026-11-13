"""Delivery records: content-addressed keys, no double upload, no double record."""

import hashlib
import io

import pytest

from forgetools import storage


class FakeBucket:
    def __init__(self):
        self.objects = {}
        self.uploads = 0

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)

    def upload_file(self, path, bucket, key, ExtraArgs=None):
        self.uploads += 1
        with open(path, "rb") as handle:
            self.objects[key] = handle.read()

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"http://bucket.invalid/{Params['Key']}?ttl={ExpiresIn}"


def test_put_is_idempotent_and_check_verifies_bytes(tmp_path):
    bucket = FakeBucket()
    asset = tmp_path / "run" / "deliverables" / "icon.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"icon-bytes")
    record = tmp_path / "run" / "deliveries.json"
    first = storage.put([asset], record, conditions={"seed": 1}, client_bucket=(bucket, "b"))
    digest = hashlib.sha256(b"icon-bytes").hexdigest()
    assert first[0]["key"] == f"forge/{digest[:2]}/{digest}.png" and first[0]["file"] == "deliverables/icon.png"
    again = storage.put([asset], record, client_bucket=(bucket, "b"))
    assert bucket.uploads == 1 and again[0]["recorded"] is False
    assert len(storage.read_record(record)["items"]) == 1
    assert storage.check(record, client_bucket=(bucket, "b"))[0]["hash_matches"] is True
    bucket.objects[first[0]["key"]] = b"tampered"
    assert storage.check(record, client_bucket=(bucket, "b"))[0]["hash_matches"] is False


def test_link_refuses_a_key_the_bucket_does_not_hold():
    bucket = FakeBucket()
    with pytest.raises(storage.LocalError, match="holds no object"):
        storage.link("forge/00/missing.png", client_bucket=(bucket, "b"))
    bucket.objects["forge/aa/x.png"] = b"x"
    assert storage.link("forge/aa/x.png", 10, client_bucket=(bucket, "b")).endswith("ttl=600")
