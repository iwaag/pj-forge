"""The condition shape and argument validation of `speech.synthesize`.

`say`/`ffmpeg` are host tools, not mocked: the real render is covered by the
run's `verify` step, not here.
"""

import pytest

from forgetools import speech
from forgetools.local import LocalError


def test_empty_text_refused(tmp_path):
    with pytest.raises(LocalError):
        speech.synthesize("   ", tmp_path / "out.wav")


def test_non_positive_rate_refused(tmp_path):
    with pytest.raises(LocalError):
        speech.synthesize("hello", tmp_path / "out.wav", rate=0)


def test_negative_pad_refused(tmp_path):
    with pytest.raises(LocalError):
        speech.synthesize("hello", tmp_path / "out.wav", pad=-1)
