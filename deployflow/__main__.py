from __future__ import annotations

import sys
from pathlib import Path

from .gui import run


def _get_project_id() -> str | None:
    if len(sys.argv) > 1:
        return sys.argv[1]
    return None


def main() -> None:
    run(_get_project_id())


if __name__ == "__main__":
    main()
