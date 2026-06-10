"""Centralized .env loading. Called once at process startup."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_LOADED = False


def load_env() -> None:
    global _LOADED
    if _LOADED:
        return
    # Walk up from this file to find a .env at the repo root.
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        env_path = parent / ".env"
        if env_path.is_file():
            load_dotenv(env_path, override=False)
            break
    _LOADED = True
