from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from deployflow.config import (
    create_project, update_project, delete_project, get_project,
    load_all_projects, detect_engine, find_export_presets, get_project_version,
)
from deployflow.settings import load_settings, save_settings, get_all_settings
from deployflow.credentials import store_credential, load_credential, delete_credential
from deployflow.engine import build_godot, build_unity, zip_build
from deployflow.uploaders import push_itch, push_steam
from deployflow.recent import load_recent_ids, add_recent, remove_recent

# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="Deploy Flow API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- In-memory build/upload log storage ---
_logs: dict[str, list[str]] = {}
_status: dict[str, str] = {}  # running | completed | error

def _log(pid: str, msg: str) -> None:
    _logs.setdefault(pid, [])
    _logs[pid].append(msg)

def _build_task(pid: str) -> None:
    _status[pid] = "running"
    _logs[pid] = []
    try:
        proj = get_project(pid)
        project_dir = Path(proj["project_path"])
        engine = proj.get("engine", "")
        preset = proj.get("godot_preset", "")
        build_path = Path(proj["build_path"]) if proj.get("build_path") else project_dir / "build"

        if engine == "godot":
            settings = load_settings()
            godot_exe = settings.get("godot_executable", "")
            build_godot(project_dir, preset, build_path, godot_exe=godot_exe, log=lambda m: _log(pid, m))
        elif engine == "unity":
            settings = load_settings()
            unity_exe = settings.get("unity_executable", "")
            build_unity(project_dir, build_path, unity_exe=unity_exe, log=lambda m: _log(pid, m))
        else:
            raise Exception(f"Unknown engine: {engine}")

        update_project(pid, {"last_build_time": __import__("datetime").datetime.now().isoformat(), "last_build_success": True})
        _status[pid] = "completed"
    except Exception as e:
        _log(pid, f"ERROR: {e}")
        _status[pid] = "error"

def _upload_itch_task(pid: str) -> None:
    _status[f"itch_{pid}"] = "running"
    _logs.setdefault(f"itch_{pid}", [])
    try:
        proj = get_project(pid)
        build_path = Path(proj["build_path"]) if proj.get("build_path") else Path(proj["project_path"]) / "build"
        target = proj.get("itch_target", "")
        push_itch(build_path, target, log=lambda m: _log(f"itch_{pid}", m))
        _status[f"itch_{pid}"] = "completed"
    except Exception as e:
        _log(f"itch_{pid}", f"ERROR: {e}")
        _status[f"itch_{pid}"] = "error"

def _upload_steam_task(pid: str) -> None:
    _status[f"steam_{pid}"] = "running"
    _logs.setdefault(f"steam_{pid}", [])
    try:
        proj = get_project(pid)
        app_id = proj.get("steam_app_id", "")
        build_path = Path(proj["build_path"]) if proj.get("build_path") else Path(proj["project_path"]) / "build"
        depot_id = proj.get("steam_depots", {}).get(proj.get("platform", "win"), "")
        push_steam(app_id, build_path, depot_id=depot_id, log=lambda m: _log(f"steam_{pid}", m))
        _status[f"steam_{pid}"] = "completed"
    except Exception as e:
        _log(f"steam_{pid}", f"ERROR: {e}")
        _status[f"steam_{pid}"] = "error"

# ===================== PROJECTS =====================
@app.get("/api/projects")
def list_projects():
    data = load_all_projects()
    projects = data.get("projects", {})
    order = data.get("order", [])
    result = []
    for pid in order:
        if pid in projects:
            p = dict(projects[pid])
            p["id"] = pid
            result.append(p)
    return result

@app.post("/api/projects")
def add_project(project_path: str):
    pid = create_project(project_path)
    return {"id": pid}

@app.get("/api/projects/{pid}")
def get_project_endpoint(pid: str):
    proj = get_project(pid)
    if not proj.get("name") and pid not in load_all_projects().get("projects", {}):
        raise HTTPException(404)
    proj["id"] = pid
    return proj

@app.put("/api/projects/{pid}")
def update_project_endpoint(pid: str, body: dict[str, Any]):
    data = load_all_projects()
    if pid not in data.get("projects", {}):
        raise HTTPException(404)
    update_project(pid, body)
    return {"ok": True}

@app.delete("/api/projects/{pid}")
def remove_project(pid: str):
    data = load_all_projects()
    if pid not in data.get("projects", {}):
        raise HTTPException(404)
    delete_project(pid)
    return {"ok": True}

@app.get("/api/projects/{pid}/detect")
def detect_project(pid: str):
    proj = get_project(pid)
    project_dir = Path(proj.get("project_path", ""))
    if not project_dir.is_dir():
        raise HTTPException(400, "Project path does not exist")
    engine = detect_engine(project_dir)
    presets = find_export_presets(project_dir) if engine == "godot" else []
    version = get_project_version(project_dir)
    return {"engine": engine, "presets": presets, "version": version}

# ===================== BUILD =====================
@app.post("/api/projects/{pid}/build")
def start_build(pid: str):
    data = load_all_projects()
    if pid not in data.get("projects", {}):
        raise HTTPException(404)
    thread = threading.Thread(target=_build_task, args=(pid,), daemon=True)
    thread.start()
    return {"ok": True, "status": "started"}

@app.get("/api/projects/{pid}/build/status")
def build_status(pid: str):
    return {"status": _status.get(pid, "idle"), "logs": _logs.get(pid, [])}

# ===================== UPLOADS =====================
@app.post("/api/projects/{pid}/upload/itch")
def start_itch_upload(pid: str):
    data = load_all_projects()
    if pid not in data.get("projects", {}):
        raise HTTPException(404)
    thread = threading.Thread(target=_upload_itch_task, args=(pid,), daemon=True)
    thread.start()
    return {"ok": True, "status": "started"}

@app.get("/api/projects/{pid}/upload/itch/status")
def itch_upload_status(pid: str):
    return {"status": _status.get(f"itch_{pid}", "idle"), "logs": _logs.get(f"itch_{pid}", [])}

@app.post("/api/projects/{pid}/upload/steam")
def start_steam_upload(pid: str):
    data = load_all_projects()
    if pid not in data.get("projects", {}):
        raise HTTPException(404)
    thread = threading.Thread(target=_upload_steam_task, args=(pid,), daemon=True)
    thread.start()
    return {"ok": True, "status": "started"}

@app.get("/api/projects/{pid}/upload/steam/status")
def steam_upload_status(pid: str):
    return {"status": _status.get(f"steam_{pid}", "idle"), "logs": _logs.get(f"steam_{pid}", [])}

# ===================== SETTINGS =====================
@app.get("/api/settings")
def get_settings():
    return get_all_settings()

@app.put("/api/settings")
def update_settings(body: dict[str, Any]):
    # Sensitive keys are handled inside save_settings
    save_settings(body)
    return {"ok": True}

@app.get("/api/settings/credentials/{key}")
def get_credential(key: str):
    return {"value": load_credential(key)}

@app.put("/api/settings/credentials/{key}")
def update_credential(key: str, value: str):
    store_credential(key, value)
    return {"ok": True}

@app.delete("/api/settings/credentials/{key}")
def remove_credential(key: str):
    delete_credential(key)
    return {"ok": True}

# ===================== ZIP =====================
@app.post("/api/projects/{pid}/zip")
def zip_build_endpoint(pid: str):
    proj = get_project(pid)
    build_path = Path(proj.get("build_path", "")) if proj.get("build_path") else Path(proj["project_path"]) / "build"
    zip_path = build_path.with_name(f"{proj.get('name', 'build')}.zip")
    try:
        result = zip_build(build_path, zip_path, log=lambda m: None)
        return {"ok": True, "path": str(result)}
    except Exception as e:
        raise HTTPException(500, str(e))

# --- Serve React frontend ---
frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

# ===================== HEALTH =====================
@app.get("/api/health")
def health():
    return {"status": "ok"}

def main():
    uvicorn.run(app, host="127.0.0.1", port=8700)

if __name__ == "__main__":
    main()
