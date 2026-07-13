from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

CONFIG_FILE = "deployflow.json"
PROJECTS_FILE = "projects.json"

DEFAULT_PROJECT: dict[str, Any] = {
    "name": "",
    "project_path": "",
    "build_path": "",
    "engine": "",
    "platform": "",
    "itch_target": "",
    "itch_url": "",
    "steam_app_id": "",
    "steam_demo_app_id": "",
    "steam_url": "",
    "steam_depots": {},
    "demo_build": False,
    "last_build_time": "",
    "last_build_success": False,
}


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


def _projects_path() -> Path:
    return _data_dir() / PROJECTS_FILE


def load_all_projects() -> dict[str, Any]:
    path = _projects_path()
    if not path.exists():
        return {"projects": {}, "order": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"projects": {}, "order": []}


def save_all_projects(data: dict[str, Any]) -> None:
    path = _projects_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def create_project(project_path: str) -> str:
    data = load_all_projects()
    pid = str(uuid.uuid4())
    proj = dict(DEFAULT_PROJECT)
    proj["name"] = Path(project_path).name
    proj["project_path"] = project_path
    # Auto-detect engine
    engine = detect_engine(Path(project_path))
    if engine:
        proj["engine"] = engine
    data["projects"][pid] = proj
    data["order"].append(pid)
    save_all_projects(data)
    return pid


def update_project(pid: str, cfg: dict[str, Any]) -> None:
    data = load_all_projects()
    if pid in data["projects"]:
        data["projects"][pid].update(cfg)
        if cfg.get("project_path"):
            data["projects"][pid]["name"] = Path(cfg["project_path"]).name
        save_all_projects(data)


def delete_project(pid: str) -> None:
    data = load_all_projects()
    data["projects"].pop(pid, None)
    data["order"] = [p for p in data["order"] if p != pid]
    save_all_projects(data)


def get_project(pid: str) -> dict[str, Any]:
    data = load_all_projects()
    proj = data["projects"].get(pid)
    if proj:
        merged = dict(DEFAULT_PROJECT)
        merged.update(proj)
        return merged
    return dict(DEFAULT_PROJECT)


def detect_engine(project_dir: Path) -> str:
    if (project_dir / "project.godot").exists():
        return "godot"
    if (project_dir / "Assets").is_dir() and (
        list(project_dir.glob("*.sln")) or list(project_dir.glob("Assembly-CSharp.csproj"))
    ):
        return "unity"
    return ""


def find_export_presets(project_dir: Path) -> list[str]:
    presets_file = project_dir / "export_presets.cfg"
    if not presets_file.exists():
        return []
    names: list[str] = []
    in_name_section = False
    for line in presets_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("[preset."):
            in_name_section = True
        elif in_name_section and stripped.startswith("name="):
            name = stripped.split("=", 1)[1].strip().strip('"')
            names.append(name)
            in_name_section = False
    return names


def get_project_version(project_dir: Path) -> str:
    godot_file = project_dir / "project.godot"
    if godot_file.exists():
        in_application = False
        for line in godot_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped == "[application]":
                in_application = True
            elif in_application and stripped.startswith("["):
                in_application = False
            elif in_application and stripped.startswith("config/version="):
                return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    unity_settings = project_dir / "ProjectSettings" / "ProjectSettings.asset"
    if unity_settings.exists():
        in_player = False
        for line in unity_settings.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped == "PlayerSettings:":
                in_player = True
            elif in_player and stripped.startswith("bundleVersion:"):
                return stripped.split(":", 1)[1].strip().strip('"').strip("'")
            elif in_player and not line.startswith(" "):
                in_player = False
    return ""


def migrate_old_projects() -> None:
    """Import old per-project deployflow.json files into the centralized store."""
    data = load_all_projects()
    if data["projects"]:
        return
    import sys as _sys
    if _sys.platform == "win32":
        recent_path = Path.home() / "AppData" / "Local" / "DeployFlow" / "recent_projects.json"
    elif _sys.platform == "darwin":
        recent_path = Path.home() / "Library" / "Application Support" / "DeployFlow" / "recent_projects.json"
    else:
        recent_path = Path.home() / ".config" / "deployflow" / "recent_projects.json"

    if not recent_path.exists():
        return

    try:
        with open(recent_path, "r", encoding="utf-8") as f:
            recent_list = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    if not isinstance(recent_list, list):
        return

    for entry in recent_list:
        path_str = entry.get("path", "") if isinstance(entry, dict) else (entry if isinstance(entry, str) else "")
        if not path_str:
            continue
        proj_path = Path(path_str)
        config_file = proj_path / CONFIG_FILE
        if not config_file.exists():
            continue
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                old_cfg = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        pid = str(uuid.uuid4())
        proj = dict(DEFAULT_PROJECT)
        proj["name"] = proj_path.name
        proj["project_path"] = str(proj_path)
        for key in old_cfg:
            if key in proj:
                proj[key] = old_cfg[key]
        if not proj.get("engine"):
            engine = detect_engine(proj_path)
            if engine:
                proj["engine"] = engine
        data["projects"][pid] = proj
        data["order"].append(pid)

    save_all_projects(data)
