"""Load KEY=VALUE pairs from a project-root ``.env`` into ``os.environ``.

Existing environment variables always win (``.env`` never overrides an
already-set key). Pure stdlib — no python-dotenv dependency.
"""
from __future__ import annotations

import os
from pathlib import Path

_LOADED = False


def _candidate_env_paths() -> list[Path]:
    """Prefer ``.env`` next to the package install / repo root, then walk cwd up."""
    paths: list[Path] = []
    # diagram2drawio/env.py -> parents[1] is the repo root when run from source
    # (and the site-packages parent when installed — still a reasonable place
    # to look, after which we fall through to cwd).
    paths.append(Path(__file__).resolve().parents[1] / ".env")
    here = Path.cwd().resolve()
    for directory in (here, *here.parents):
        paths.append(directory / ".env")
        # Stop at filesystem root; parents of / is empty on POSIX.
        if directory.parent == directory:
            break
    # Deduplicate while preserving order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def _parse_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export ") :].lstrip()
    if "=" not in line:
        return None
    key, _, value = line.partition("=")
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return key, value


def load_dotenv(dotenv_path: str | Path | None = None, *, override: bool = False) -> Path | None:
    """Load the first readable ``.env`` found.

    Returns the path that was loaded, or ``None`` if none existed.
    Safe to call repeatedly; subsequent calls are no-ops unless
    ``dotenv_path`` is given explicitly.
    """
    global _LOADED
    if dotenv_path is None and _LOADED:
        return None

    candidates = [Path(dotenv_path)] if dotenv_path is not None else _candidate_env_paths()
    loaded_from: Path | None = None
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in text.splitlines():
            parsed = _parse_line(raw)
            if parsed is None:
                continue
            key, value = parsed
            if override or key not in os.environ:
                os.environ[key] = value
        loaded_from = path
        break

    if dotenv_path is None:
        _LOADED = True
    return loaded_from
