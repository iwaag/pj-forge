from pathlib import Path

import pytest

from forgetools import local


def test_copy_location_names_the_project_workspace(tmp_path, monkeypatch):
    monkeypatch.delenv("FORGE_LOCAL", raising=False)
    tree = tmp_path / "pj-forge" / ".agdev" / "runs" / "provide" / "run-001" / "source" / "devdocs"
    tree.mkdir(parents=True)
    assert local.local_dir(tree) == tmp_path / "pj-forge"


def test_project_root_without_a_copy(tmp_path, monkeypatch):
    monkeypatch.delenv("FORGE_LOCAL", raising=False)
    monkeypatch.delenv("AGDEV_PROJECT_WORKSPACE", raising=False)
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "project.yaml").write_text("id: forge\n")
    (tmp_path / "source" / "catalog").mkdir()
    monkeypatch.setattr(local, "__file__", str(tmp_path / "elsewhere.py"))
    assert local.local_dir(tmp_path / "source" / "catalog") == tmp_path


def test_explicit_folder_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_LOCAL", str(tmp_path))
    assert local.local_dir(Path("/")) == tmp_path


def test_missing_env_file_is_a_one_line_refusal(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_LOCAL", str(tmp_path))
    with pytest.raises(local.LocalError, match="forge.env"):
        local.load_env()
