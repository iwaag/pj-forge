"""The interruption boundary: a recorded job is never queued twice and never collected twice."""

import json

import pytest

from forgetools import comfy


class FakeComfy:
    """Just enough of ComfyUI's /prompt, /queue, /history and /view."""

    def __init__(self):
        self.posted = []          # prompt ids received
        self.finished = {}        # prompt id -> outputs
        self.fail_next_post = False
        self.views = 0

    def post_prompt(self, base, graph, prompt_id):
        if self.fail_next_post:
            self.fail_next_post = False
            raise KeyboardInterrupt("interrupted between the record and the server's answer")
        self.posted.append(prompt_id)
        return prompt_id

    def state(self, base, prompt_id):
        if prompt_id in self.finished:
            return {"state": "finished", "outputs": self.finished[prompt_id]}
        if prompt_id in self.posted:
            return {"state": "running"}
        return {"state": "unknown"}


@pytest.fixture
def fake(tmp_path, monkeypatch):
    server = FakeComfy()
    monkeypatch.setattr(comfy, "base_url", lambda: "http://comfy.invalid")
    monkeypatch.setattr(comfy, "_post", server.post_prompt)
    monkeypatch.setattr(comfy, "server_state", server.state)
    graph = {"1": {"class_type": "SaveImage", "inputs": {}}}
    workflow = tmp_path / "graph.json"
    workflow.write_text(json.dumps(graph))

    class Response:
        content = b"PNGDATA"

        def raise_for_status(self):
            pass

    def get(url, timeout):
        server.views += 1
        return Response()

    monkeypatch.setattr(comfy.requests, "get", get)
    server.workflow = workflow
    return server


def test_submit_writes_the_record_before_queueing_and_refuses_a_second_submit(tmp_path, fake):
    record = tmp_path / "jobs" / "a.json"
    first = comfy.submit(record, None, None, {}, workflow=fake.workflow)
    assert first["state"] == "submitted" and fake.posted == [first["prompt_id"]]
    with pytest.raises(comfy.LocalError, match="already names job"):
        comfy.submit(record, None, None, {}, workflow=fake.workflow)
    assert len(fake.posted) == 1


def test_interrupted_submit_is_completed_with_the_same_id_only_if_the_server_never_got_it(tmp_path, fake):
    record = tmp_path / "jobs" / "b.json"
    fake.fail_next_post = True
    with pytest.raises(KeyboardInterrupt):
        comfy.submit(record, None, None, {}, workflow=fake.workflow)
    saved = comfy.read(record)
    assert saved["state"] == "submitting" and fake.posted == []
    again = comfy.submit(record, None, None, {}, workflow=fake.workflow)
    assert again["prompt_id"] == saved["prompt_id"] and fake.posted == [saved["prompt_id"]]


def test_a_submitting_record_the_server_already_has_is_not_queued_again(tmp_path, fake):
    record = tmp_path / "jobs" / "c.json"
    fake.fail_next_post = True
    with pytest.raises(KeyboardInterrupt):
        comfy.submit(record, None, None, {}, workflow=fake.workflow)
    saved = comfy.read(record)
    fake.posted.append(saved["prompt_id"])  # it did arrive before the interruption
    result = comfy.submit(record, None, None, {}, workflow=fake.workflow)
    assert result["state"] == "submitted" and fake.posted.count(saved["prompt_id"]) == 1
    assert "not queued again" in result["notes"][-1]


def test_collect_waits_for_nothing_by_default_and_then_collects_once(tmp_path, fake):
    record = tmp_path / "jobs" / "d.json"
    job = comfy.submit(record, None, None, {}, workflow=fake.workflow)
    early = comfy.collect(record, tmp_path / "out")
    assert early["collected"] is False and fake.views == 0
    fake.finished[job["prompt_id"]] = [{"filename": "x_00001_.png", "subfolder": "", "type": "output"}]
    first = comfy.collect(record, tmp_path / "out")
    assert first["collected"] is True and fake.views == 1
    second = comfy.collect(record, tmp_path / "out")
    assert second["collected"] is False and "already collected" in second["reason"] and fake.views == 1
    saved = comfy.read(record)
    assert saved["state"] == "collected" and saved["outputs"][0]["file"] == "../out/x_00001_.png"


def test_a_collected_file_lost_on_disk_is_fetched_again_from_the_same_job(tmp_path, fake):
    record = tmp_path / "jobs" / "e.json"
    job = comfy.submit(record, None, None, {}, workflow=fake.workflow)
    fake.finished[job["prompt_id"]] = [{"filename": "y.png", "subfolder": "", "type": "output"}]
    comfy.collect(record, tmp_path / "out")
    (tmp_path / "out" / "y.png").unlink()
    again = comfy.collect(record, tmp_path / "out")
    assert again["collected"] is True and fake.posted == [job["prompt_id"]]


def test_flux2_preset_sets_the_owned_nodes(tmp_path, monkeypatch):
    graph = {
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "25": {"class_type": "RandomNoise", "inputs": {"noise_seed": 0}},
        "26": {"class_type": "FluxGuidance", "inputs": {"guidance": 0}},
        "47": {"class_type": "EmptyFlux2LatentImage", "inputs": {}},
        "48": {"class_type": "Flux2Scheduler", "inputs": {"steps": ["90", 0]}},
        "90": {"class_type": "ComfySwitchNode", "inputs": {"on_true": ["99", 0]}},
        "99": {"class_type": "PrimitiveInt", "inputs": {"value": 20}},
        "104": {"class_type": "PrimitiveBoolean", "inputs": {"value": False}},
        "7": {"class_type": "UNETLoader", "inputs": {"unet_name": "u"}},
        "8": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": "l"}},
    }
    monkeypatch.setenv("FORGE_LOCAL", str(tmp_path))
    (tmp_path / "comfy").mkdir()
    (tmp_path / "comfy" / "flux2-scenery.json").write_text(json.dumps(graph))
    built, parameters = comfy.build("flux2-scenery", "a forest", {"seed": 7, "steps": 8}, None)
    assert built["6"]["inputs"]["text"] == "a forest" and built["25"]["inputs"]["noise_seed"] == 7
    assert built["99"]["inputs"]["value"] == 8 and built["104"]["inputs"]["value"] is True
    assert parameters["width"] == 1344 and parameters["unet"] == "u"
