"""Local wrapper for the Indie Tools shared database.

Lets Deploy Flow read/write the *unified* project records (name,
description, project_path, engine, etc.) in the shared `indie_tools.db`,
while still running 100% standalone when the shared library is not installed.

Deploy Flow's own project store is `projects.json`; each entry gains a
`project_id` that links it to a shared `projects` row. When `indie_tools_shared`
is importable we mirror the relevant fields two-way; when it is not, every
function silently no-ops so Deploy Flow keeps using its local JSON.
No other app or the dashboard is ever required.
"""

from __future__ import annotations

import os
import uuid
from typing import Optional

_SHARED_DB = None
_SHARED_AVAILABLE = None


def is_available() -> bool:
    """True if the shared library + DB are reachable."""
    global _SHARED_AVAILABLE, _SHARED_DB
    if _SHARED_AVAILABLE is None:
        try:
            from indie_tools_shared import IndieToolsDB, get_db_path  # noqa: F401

            _SHARED_DB = IndieToolsDB()
            _SHARED_AVAILABLE = True
        except Exception:
            _SHARED_AVAILABLE = False
    return _SHARED_AVAILABLE


def _db():
    global _SHARED_DB
    if _SHARED_DB is None:
        from indie_tools_shared import IndieToolsDB

        _SHARED_DB = IndieToolsDB()
    return _SHARED_DB


APP_KEY = "deploy_flow"


def new_project_id() -> str:
    return str(uuid.uuid4())


def ensure_project(
    project_id: str,
    name: str,
    description: str = "",
    project_path: str = "",
    engine: str = "",
) -> Optional[str]:
    """Create the shared project row (with the given id) if missing,
    otherwise update its identity fields so the two stores stay in sync.
    Returns project_id."""
    if not is_available() or not project_id:
        return project_id
    try:
        db = _db()
        if db.get_project(project_id) is None:
            from indie_tools_shared import get_db_path
            import sqlite3 as _sqlite
            import json as _json
            from datetime import datetime

            conn = _sqlite.connect(str(get_db_path()))
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO projects
                       (id, name, description, cover_art, steam_appid,
                        project_path, engine, tags, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        project_id,
                        name,
                        description,
                        "",
                        None,
                        project_path,
                        engine,
                        _json.dumps([]),
                        datetime.now().isoformat(),
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        else:
            update_project_meta(
                project_id,
                name=name,
                description=description,
                project_path=project_path,
                engine=engine,
            )
        return project_id
    except Exception:
        return project_id


def get_project_meta(project_id: str) -> Optional[dict]:
    if not is_available() or not project_id:
        return None
    try:
        p = _db().get_project(project_id)
        if p is None:
            return None
        return {
            "name": p.name,
            "description": p.description,
            "cover_art": p.cover_art,
            "steam_appid": p.steam_appid,
            "project_path": p.project_path,
            "engine": p.engine,
            "tags": p.tags,
        }
    except Exception:
        return None


def update_project_meta(
    project_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    project_path: Optional[str] = None,
    engine: Optional[str] = None,
) -> None:
    if not is_available() or not project_id:
        return
    try:
        updates = {}
        if name is not None:
            updates["name"] = name
        if description is not None:
            updates["description"] = description
        if project_path is not None:
            updates["project_path"] = project_path
        if engine is not None:
            updates["engine"] = engine
        if updates:
            _db().update_project(project_id, **updates)
    except Exception:
        pass


def delete_project(project_id: str) -> None:
    if not is_available() or not project_id:
        return
    try:
        _db().delete_project(project_id)
    except Exception:
        pass


def get_setting(project_id: str, key: str, default=None):
    if not is_available() or not project_id:
        return default
    try:
        settings = _db().get_settings(project_id, APP_KEY)
        return settings.get(key, default)
    except Exception:
        return default


def set_setting(project_id: str, key: str, value) -> None:
    if not is_available() or not project_id:
        return
    try:
        _db().set_setting(project_id, APP_KEY, key, value)
    except Exception:
        pass
