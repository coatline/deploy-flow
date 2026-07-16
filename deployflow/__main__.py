from __future__ import annotations

import sys
from pathlib import Path

from .gui import run

try:
    from indie_tools_shared import IndieToolsDB, get_db_path
    _shared_db = IndieToolsDB()
    _projects = _shared_db.get_all_projects()
    print(f"[Indie Tools] Connected to shared DB at {get_db_path()} ({len(_projects)} projects)")
except ImportError:
    print("[Indie Tools] Shared library not installed — running standalone")
except Exception as e:
    print(f"[Indie Tools] Couldn't connect to shared DB — {e}")


def _get_project_id() -> str | None:
    if len(sys.argv) > 1:
        return sys.argv[1]
    return None


def main() -> None:
    run(_get_project_id())


if __name__ == "__main__":
    main()
