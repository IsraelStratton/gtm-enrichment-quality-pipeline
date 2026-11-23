"""Call the routing engine (engine/routing.js) from Python.

The engine is JavaScript because the same file runs inside the n8n Code nodes. Python
reaches it through engine/cli.js, so the live run, the tests and (in chapter 6) the eval
all use exactly the code that n8n runs.

    from routing_engine import Engine
    eng = Engine()
    pb = eng.call("parsePlaybook", PLAYBOOK.read_text(encoding="utf-8"))
    req = eng.call("buildRequest", pb, lead, "claude-haiku-5-5")
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
ENGINE_JS = REPO / "engine" / "routing.js"
CLI_JS = REPO / "engine" / "cli.js"
SKIN = REPO / "skins" / "lead-routing"
PLAYBOOK = SKIN / "lead-routing-playbook" / "SKILL.md"


class EngineError(RuntimeError):
    pass


class Ref(dict):
    """Use the result of an earlier call in the same batch: Ref(0) is the first result."""

    def __init__(self, index: int):
        super().__init__({"$ref": index})


class Engine:
    def __init__(self, node: str | None = None):
        self.node = node or shutil.which("node")
        if not self.node:
            raise EngineError("node is not installed; the routing engine needs Node.js 18 or later")

    def batch(self, calls: list[tuple[str, list[Any]]]) -> list[Any]:
        payload = json.dumps({"calls": [{"fn": fn, "args": args} for fn, args in calls]})
        out = subprocess.run([self.node, str(CLI_JS)], input=payload, capture_output=True, text=True, check=False)
        if out.returncode != 0 and not out.stdout:
            raise EngineError(out.stderr.strip() or f"node exited with {out.returncode}")
        reply = json.loads(out.stdout)
        if not reply["ok"]:
            raise EngineError(reply["error"])
        return reply["results"]

    def call(self, fn: str, *args: Any) -> Any:
        return self.batch([(fn, list(args))])[0]


def read_playbook(path: Path = PLAYBOOK) -> str:
    return path.read_text(encoding="utf-8")
