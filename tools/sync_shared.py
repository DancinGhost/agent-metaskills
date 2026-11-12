#!/usr/bin/env python3
"""Vendor shared/skillmeta.py into every skill that has a scripts/ directory.

Each skill must work when copied out of this repository on its own, so the
shared helpers are copied in as scripts/_skillmeta.py rather than imported
from a common location.

    python3 tools/sync_shared.py          # copy
    python3 tools/sync_shared.py --check  # exit 1 if any copy is stale
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "shared" / "skillmeta.py"
VENDORED_NAME = "_skillmeta.py"


def targets() -> list:
    return sorted(
        scripts / VENDORED_NAME
        for scripts in (ROOT / "skills").glob("*/scripts")
        if scripts.is_dir()
    )


def main(argv: list) -> int:
    check = "--check" in argv
    source = SOURCE.read_text(encoding="utf-8")
    stale = []
    for target in targets():
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current == source:
            continue
        stale.append(target)
        if not check:
            target.write_text(source, encoding="utf-8")
            print(f"updated {target.relative_to(ROOT)}")
    if check and stale:
        for target in stale:
            print(f"stale: {target.relative_to(ROOT)}", file=sys.stderr)
        print("run: python3 tools/sync_shared.py", file=sys.stderr)
        return 1
    if not stale:
        print("vendored copies are up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
