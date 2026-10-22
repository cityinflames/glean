"""Where Glean keeps its files. The workshop stays in this folder. A packaged copy uses the user's AppData."""

import os
import sys
from pathlib import Path


def frozen():
    return bool(getattr(sys, "frozen", False))


def resource_dir():
    if frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def user_dir():
    if frozen():
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Glean"
    else:
        base = Path(__file__).resolve().parent
    base.mkdir(parents=True, exist_ok=True)
    return base


def ffmpeg_cmd():
    for candidate in (
        resource_dir() / "ffmpeg.exe",
        Path(sys.executable).parent / "ffmpeg.exe",
    ):
        if candidate.exists():
            return str(candidate)
    return "ffmpeg"
