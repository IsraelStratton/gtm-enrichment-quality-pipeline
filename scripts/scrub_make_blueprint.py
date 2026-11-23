#!/usr/bin/env python3
"""Clean a Make blueprint export for the public repo.

Replaces the private identifiers with placeholders and refuses a file that
still holds an email address or a webhook URL:

  parameters.hook          -> "MAKE_HOOK_ID"
  parameters.oAuthAccount  -> "MAKE_CONNECTION_ID"
  Google Sheets ID in URLs -> "SPREADSHEET_ID"

  python scripts/scrub_make_blueprint.py ~/Downloads/<export>.blueprint.json

Writes slice/make/slice-scenario.blueprint.json. Exit codes: 0 written, 2 refused.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUTPUT = REPO / "slice" / "make" / "slice-scenario.blueprint.json"
PLACEHOLDERS = {"hook": "MAKE_HOOK_ID", "oAuthAccount": "MAKE_CONNECTION_ID"}
SHEET_IN_URL = re.compile(r"(spreadsheets/)[A-Za-z0-9_-]{20,}")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z.]{2,}")
HOOK_URL = re.compile(r"hook\.[a-z0-9]+\.make\.com/[A-Za-z0-9]+")


class Refused(Exception):
    pass


def scrub(node):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in PLACEHOLDERS and isinstance(v, (int, str)) and not isinstance(v, bool):
                out[k] = PLACEHOLDERS[k]
            else:
                out[k] = scrub(v)
        return out
    if isinstance(node, list):
        return [scrub(v) for v in node]
    if isinstance(node, str):
        return SHEET_IN_URL.sub(r"\1SPREADSHEET_ID", node)
    return node


def clean(blueprint: dict) -> dict:
    out = scrub(blueprint)
    text = json.dumps(out)
    if EMAIL.search(text):
        raise Refused("the blueprint holds an email address")
    if HOOK_URL.search(text):
        raise Refused("the blueprint holds a Make webhook URL")
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    try:
        out = clean(json.loads(Path(argv[0]).read_text(encoding="utf-8")))
    except (Refused, OSError, ValueError) as e:
        print(f"REFUSED {e}")
        return 2
    OUTPUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
