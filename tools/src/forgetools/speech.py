"""Speech: one WAV per line of text through macOS's built-in `say` and `ffmpeg`.

System text-to-speech, not acting: intelligible, flat prosody. "Calm, gentle"
delivery is not controllable beyond voice choice and speaking rate. No model,
service or paid API — `say` and `ffmpeg` are host tools already relied on
elsewhere in this project.

Built for one request for Japanese voice lines; acted delivery (neural TTS,
a paid cloud voice) was left open. Not documented or checked in this
publication.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .local import LocalError
from .storage import sha256_of

DEFAULT_VOICE = "Kyoko"
DEFAULT_RATE = 48000
DEFAULT_PAD = 0.3


def synthesize(text: str, out: Path, *, voice: str = DEFAULT_VOICE, rate: int = DEFAULT_RATE,
               pad: float = DEFAULT_PAD) -> dict:
    """Render `text` to a mono WAV at `out`: `say -v voice` then `ffmpeg` resample + pad."""
    if not text.strip():
        raise LocalError("text is empty")
    if rate <= 0:
        raise LocalError("--rate must be positive")
    if pad < 0:
        raise LocalError("--pad cannot be negative")

    out.parent.mkdir(parents=True, exist_ok=True)
    aiff = out.with_suffix(".say.aiff")
    try:
        say = subprocess.run(["say", "-v", voice, "-o", str(aiff), text],
                             capture_output=True, text=True)
        if say.returncode != 0:
            raise LocalError(f"say failed (voice {voice!r}): {say.stderr.strip() or say.returncode}")
        if not aiff.is_file():
            raise LocalError(f"say produced no output for voice {voice!r}")

        pad_filter = f"apad=pad_dur={pad},areverse,apad=pad_dur={pad},areverse" if pad > 0 else "anull"
        ffmpeg = subprocess.run(
            ["ffmpeg", "-y", "-i", str(aiff), "-ar", str(rate), "-ac", "1", "-af", pad_filter, str(out)],
            capture_output=True, text=True,
        )
        if ffmpeg.returncode != 0:
            raise LocalError(f"ffmpeg failed: {ffmpeg.stderr.strip()[-500:]}")
    finally:
        aiff.unlink(missing_ok=True)

    if not out.is_file():
        raise LocalError(f"ffmpeg produced no output at {out}")
    conditions = {"route": "say+ffmpeg", "text": text, "voice": voice, "rate": rate, "pad_seconds": pad}
    return {"path": str(out), "sha256": sha256_of(out), "conditions": conditions}
