from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable

NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class BuildError(Exception):
    pass


def _run(cmd: list[str], cwd: Path | None = None, log: Callable[[str], None] | None = None) -> None:
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=NO_WINDOW,
    )
    for line in proc.stdout or []:
        if log:
            log(line.rstrip("\n"))
    proc.wait()
    if proc.returncode != 0:
        raise BuildError(f"Command failed (exit {proc.returncode}): {' '.join(cmd)}")


def build_godot(
    project_dir: Path,
    preset: str,
    output_path: Path,
    godot_exe: str = "",
    log: Callable[[str], None] | None = None,
) -> Path:
    exe = godot_exe or shutil.which("godot") or shutil.which("godot4") or ""
    if not exe:
        raise BuildError("Godot executable not found. Set 'godot_executable' in config or add godot to PATH.")
    if not preset:
        raise BuildError("No export preset selected.")
    output_path.mkdir(parents=True, exist_ok=True)
    # Web exports require a file path, not a directory
    output_file = output_path / "index.html" if "web" in preset.lower() else output_path
    cmd = [
        exe,
        "--headless",
        "--path", str(project_dir),
        "--export-release", preset,
        str(output_file),
    ]
    if log:
        log(f"Running: {' '.join(cmd)}")
    _run(cmd, cwd=project_dir, log=log)
    return output_path


def build_unity(
    project_dir: Path,
    build_path: Path,
    unity_exe: str = "",
    log: Callable[[str], None] | None = None,
) -> Path:
    exe = unity_exe or shutil.which("Unity") or ""
    if not exe:
        raise BuildError("Unity executable not found. Set 'unity_executable' in config or add Unity to PATH.")
    build_path.mkdir(parents=True, exist_ok=True)
    project_name = project_dir.name
    output_exe = build_path / f"{project_name}.exe"
    cmd = [
        exe,
        "-batchmode",
        "-nographics",
        "-projectPath", str(project_dir),
        "-buildWindows64Player", str(output_exe),
        "-logFile", str(build_path / "unity_build.log"),
    ]
    if log:
        log(f"Running: {' '.join(cmd)}")
    _run(cmd, cwd=project_dir, log=log)
    return build_path


def zip_build(source_dir: Path, zip_path: Path, log: Callable[[str], None] | None = None) -> Path:
    if not source_dir.is_dir():
        raise BuildError(f"Build output not found: {source_dir}")
    if log:
        log(f"Packaging {source_dir} -> {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in source_dir.rglob("*"):
            if file.is_file():
                arcname = file.relative_to(source_dir)
                zf.write(file, arcname)
    if log:
        log(f"Archive created: {zip_path} ({zip_path.stat().st_size:,} bytes)")
    return zip_path
