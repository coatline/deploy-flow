from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .credentials import store_credential, load_credential

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "godot_executable": "",
    "unity_executable": "",
    "steam_username": "",
    "steam_script_path": "",
}

SENSITIVE_KEYS = {"itch_api_key", "steam_token"}


def _data_dir() -> Path:
    import sys
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Local" / "DeployFlow"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "DeployFlow"
    else:
        base = Path.home() / ".config" / "deployflow"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _settings_path() -> Path:
    return _data_dir() / SETTINGS_FILE


def load_settings() -> dict[str, Any]:
    path = _settings_path()
    if not path.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_SETTINGS)
    merged = dict(DEFAULT_SETTINGS)
    merged.update(data)
    for key in SENSITIVE_KEYS:
        merged.pop(key, None)
    return merged


def save_settings(settings: dict[str, Any]) -> None:
    for key in SENSITIVE_KEYS:
        val = settings.pop(key, None)
        if val:
            store_credential(key, val)
    path = _settings_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def get_setting(key: str) -> str:
    if key in SENSITIVE_KEYS:
        return load_credential(key)
    return load_settings().get(key, DEFAULT_SETTINGS.get(key, ""))


def get_all_settings() -> dict[str, str]:
    result = load_settings()
    for key in SENSITIVE_KEYS:
        result[key] = load_credential(key)
    return result
