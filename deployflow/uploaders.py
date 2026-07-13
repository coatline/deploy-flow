from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .credentials import load_credential
from .settings import load_settings

NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class UploadError(Exception):
    pass


def _run(cmd: list[str], log: Callable[[str], None] | None = None, env: dict[str, str] | None = None) -> int:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=NO_WINDOW,
        env=env,
    )
    for line in proc.stdout or []:
        if log:
            log(line.rstrip("\n"))
    proc.wait()
    return proc.returncode


def push_itch(
    build_path: Path,
    target: str,
    log: Callable[[str], None] | None = None,
) -> None:
    exe = shutil.which("butler")
    if not exe:
        raise UploadError("butler not found in PATH. Install butler from https://itch.io/docs/butler/")
    if not target:
        raise UploadError("No itch.io target set. Configure 'itch_target' as user/game:channel.")
    if not build_path.exists():
        raise UploadError(f"Build path does not exist: {build_path}")

    api_key = load_credential("itch_api_key")

    env = None
    if api_key:
        env = {**{k: v for k, v in os.environ.items()}, "BUTLER_API_KEY": api_key}

    cmd = [exe, "push", str(build_path), target]

    if log:
        log(f"Uploading to itch.io: {target}")
    rc = _run(cmd, log=log, env=env)
    if rc != 0:
        raise UploadError(f"butler push failed (exit {rc})")
    if log:
        log("itch.io upload complete!")


def push_steam(
    app_id: str,
    content_dir: Path,
    script_path: Path | None = None,
    depot_id: str | None = None,
    log: Callable[[str], None] | None = None,
) -> None:
    exe = shutil.which("steamcmd")
    if not exe:
        raise UploadError("steamcmd not found in PATH. Install SteamCMD from https://partner.steamgames.com/doc/sdk/uploading")
    if not app_id:
        raise UploadError("No Steam App ID set. Configure 'steam_app_id' in config.")
    if not content_dir.is_dir():
        raise UploadError(f"Build directory does not exist: {content_dir}")

    settings = load_settings()
    steam_user = settings.get("steam_username", "")
    steam_token = load_credential("steam_token")

    vdf_script = script_path
    if vdf_script is None:
        vdf_script = content_dir / "app_build.vdf"
        _write_steam_vdf(vdf_script, app_id, content_dir, depot_id=depot_id)

    if steam_user and steam_token:
        login_args = ["+login", steam_user, steam_token]
    elif steam_user:
        login_args = ["+login", steam_user]
    else:
        login_args = ["+login", "anonymous"]

    cmd = [exe, *login_args, "+run_app_build", str(vdf_script), "+quit"]

    if log:
        log(f"Uploading to Steam (App ID: {app_id})...")
    rc = _run(cmd, log=log)
    if rc != 0:
        raise UploadError(f"steamcmd failed (exit {rc})")
    if log:
        log("Steam upload complete!")


def _write_steam_vdf(path: Path, app_id: str, content_path: Path, depot_id: str | None = None) -> None:
    depot = depot_id or str(int(app_id) + 1)
    p = str(content_path).replace("\\", "/")
    vdf = f'''"AppBuild"
{{
    "AppID" "{app_id}"
    "Desc" "DeployFlow auto-build"
    "ContentRoot" "{p}"
    "BuildOutput" "{p}"
    "Depots"
    {{
        "{depot}"
        {{
            "FileMapping"
            {{
                "LocalPath" "*"
                "DepotPath" "."
                "Recursive" "1"
            }}
        }}
    }}
}}
'''
    path.write_text(vdf, encoding="utf-8")
