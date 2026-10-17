"""Settings that outlive a run: the plasmid library folder and recent files.

Stored as JSON next to the user's other application data
(`~/Library/Application Support/DNA Cloning Assistant/settings.json` on macOS,
`~/.config/dna-cloning-assistant/settings.json` elsewhere), so the folder the
user picks is still there the next time the app opens.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

APP_DIR_NAME = "DNA Cloning Assistant"
MAX_RECENT = 12
MAX_LISTED = 500
SUFFIXES = (".dna",)


def config_dir() -> str:
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
        return os.path.join(base, APP_DIR_NAME)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "dna-cloning-assistant")


def config_path() -> str:
    return os.path.join(config_dir(), "settings.json")


def load() -> dict[str, Any]:
    try:
        with open(config_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data: dict[str, Any]) -> None:
    os.makedirs(config_dir(), exist_ok=True)
    tmp = config_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, config_path())


def library_dir() -> str | None:
    path = load().get("library_dir")
    return path if isinstance(path, str) and path else None


def set_library_dir(path: str) -> str:
    """Remember `path` as the plasmid library; returns the absolute path."""
    full = os.path.abspath(os.path.expanduser(path.strip()))
    if not os.path.isdir(full):
        raise ValueError(f"폴더를 찾을 수 없습니다: {full}")
    data = load()
    data["library_dir"] = full
    save(data)
    return full


def clear_library_dir() -> None:
    data = load()
    data.pop("library_dir", None)
    save(data)


def note_recent(path: str) -> None:
    full = os.path.abspath(path)
    data = load()
    recent = [p for p in data.get("recent_files", []) if isinstance(p, str) and p != full]
    data["recent_files"] = [full] + recent[:MAX_RECENT - 1]
    try:
        save(data)
    except OSError:
        pass            # a read-only home should not break opening a file


def recent_files() -> list[dict[str, Any]]:
    out = []
    for path in load().get("recent_files", []):
        if isinstance(path, str) and os.path.isfile(path):
            out.append({"name": os.path.basename(path), "path": path})
    return out


def list_library(path: str | None = None) -> dict[str, Any]:
    """List the .dna files in the library folder, newest first.

    Walks one level of subfolders so a lab folder split by project still shows
    everything; `folder` on each entry says where it came from.
    """
    root = path or library_dir()
    if not root:
        return {"dir": None, "files": [], "error": None}
    if not os.path.isdir(root):
        return {"dir": root, "files": [], "error": f"폴더를 찾을 수 없습니다: {root}"}

    files: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        depth = 0 if dirpath == root else os.path.relpath(dirpath, root).count(os.sep) + 1
        # one level of subfolders, so a folder split by project still shows up
        dirnames[:] = [] if depth >= 1 else [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if not name.lower().endswith(SUFFIXES) or name.startswith("."):
                continue
            full = os.path.join(dirpath, name)
            try:
                stat = os.stat(full)
            except OSError:
                continue
            files.append({
                "name": name,
                "path": full,
                "folder": "" if dirpath == root else os.path.relpath(dirpath, root),
                "size": stat.st_size,
                "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                "modified_ts": stat.st_mtime,
            })
            if len(files) >= MAX_LISTED:
                break
        if len(files) >= MAX_LISTED:
            break
    files.sort(key=lambda f: f["modified_ts"], reverse=True)
    return {"dir": root, "files": files, "error": None,
            "truncated": len(files) >= MAX_LISTED}
