from __future__ import annotations

from .config import load_all_projects, save_all_projects


def load_recent_ids() -> list[str]:
    data = load_all_projects()
    return data.get("order", [])


def add_recent(pid: str) -> None:
    data = load_all_projects()
    order = data.get("order", [])
    if pid in order:
        order.remove(pid)
    order.insert(0, pid)
    data["order"] = order
    save_all_projects(data)


def remove_recent(pid: str) -> None:
    data = load_all_projects()
    data["order"] = [p for p in data.get("order", []) if p != pid]
    save_all_projects(data)
