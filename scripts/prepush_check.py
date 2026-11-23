#!/usr/bin/env python3
"""Check the commits about to be pushed. Run it before every push; the repo is public.

For every outgoing commit (origin/<branch>..HEAD by default):
  - author and committer email must be a GitHub no-reply address
  - the message must carry no agent co-author, attribution or session lines
For every line the outgoing commits add:
  - no value from the local .env (keys, tracker ID, webhook URLs and keys)
  - no real-looking email address (only example domains are allowed)
  - no Google OAuth client ID or secret
  - no string listed in .prepush-private.local (git-ignored: tool IDs and other private values)

Findings name the file or commit, never the value.

  python scripts/prepush_check.py                     # origin/<current branch>..HEAD
  python scripts/prepush_check.py --range origin/v2..HEAD

Exit codes: 0 clean, 1 findings, 2 could not run.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PRIVATE_LIST = REPO / ".prepush-private.local"
NOREPLY = re.compile(r"^[A-Za-z0-9._%+-]+@users\.noreply\.github\.com$")
AGENT_LINES = re.compile(
    r"^\s*(co-authored-by:|claude-session|session-id:)|generated with \[?claude|claude\.com/claude-code|noreply@anthropic\.com",
    re.I | re.M,
)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
ALLOWED_EMAIL = re.compile(r"@(?:[A-Za-z0-9-]+\.)*(example\.(com|org|net)|[A-Za-z0-9-]+\.example)$", re.I)
GOOGLE_CLIENT_ID = re.compile(r"\d{6,}-[a-z0-9]{20,}\.apps\.googleusercontent\.com")
GOOGLE_CLIENT_SECRET = re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}")
NON_SECRET_ENV_KEYS = {"HUBSPOT_BASE_URL", "HUBSPOT_APP_HOST", "HUBSPOT_PORTAL_ID", "N8N_BASE_URL"}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout


def check_identity(sha: str, author: str, committer: str) -> list[str]:
    out = []
    if not NOREPLY.match(author):
        out.append(f"{sha}: author email is not a GitHub no-reply address")
    if not NOREPLY.match(committer):
        out.append(f"{sha}: committer email is not a GitHub no-reply address")
    return out


def check_message(sha: str, message: str) -> list[str]:
    return [f"{sha}: message has an agent co-author, attribution or session line"] if AGENT_LINES.search(message) else []


def added_lines_by_file(diff: str) -> dict[str, list[str]]:
    files: dict[str, list[str]] = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("+") and current:
            files.setdefault(current, []).append(line[1:])
    return files


def scan_added(files: dict[str, list[str]], private: dict[str, str]) -> list[str]:
    out = []
    for name, lines in files.items():
        text = "\n".join(lines)
        for label, value in private.items():
            if value and value in text:
                out.append(f"{name}: holds a private value ({label})")
        if any(not ALLOWED_EMAIL.search(m) for m in EMAIL.findall(text)):
            out.append(f"{name}: holds a real-looking email address")
        if GOOGLE_CLIENT_ID.search(text):
            out.append(f"{name}: holds a Google OAuth client ID")
        if GOOGLE_CLIENT_SECRET.search(text):
            out.append(f"{name}: holds a Google OAuth client secret")
    return out


def private_values() -> dict[str, str]:
    values = {}
    env = REPO / ".env"
    if env.exists():
        from dotenv import dotenv_values

        for k, v in dotenv_values(env).items():
            if v and len(v) >= 8 and k not in NON_SECRET_ENV_KEYS:
                values[f".env {k}"] = v
    if PRIVATE_LIST.exists():
        for i, line in enumerate(PRIVATE_LIST.read_text(encoding="utf-8").splitlines(), 1):
            value = line.split("#", 1)[0].strip()
            if len(value) >= 6:
                values[f"{PRIVATE_LIST.name} line {i}"] = value
    return values


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--range", help="commit range to check (default: origin/<current branch>..HEAD)")
    args = ap.parse_args(argv)
    try:
        rng = args.range or f"origin/{git('rev-parse', '--abbrev-ref', 'HEAD').strip()}..HEAD"
        shas = git("rev-list", "--reverse", rng).split()
    except subprocess.CalledProcessError as e:
        print(f"CANNOT RUN {e.stderr.strip() or e}")
        return 2
    if not shas:
        print(f"Nothing to push in {rng}.")
        return 0
    findings = []
    for sha in shas:
        author, committer = git("log", "-1", "--format=%ae%n%ce", sha).splitlines()
        findings += check_identity(sha[:7], author, committer)
        findings += check_message(sha[:7], git("log", "-1", "--format=%B", sha))
    findings += scan_added(added_lines_by_file(git("diff", rng.replace("..", "...", 1) if "..." not in rng else rng)), private_values())
    print(f"Checked {len(shas)} commit(s) in {rng}.")
    for f in findings:
        print(f"FAIL {f}")
    if not findings:
        print("PASS no-reply author and committer, no agent lines, no private values in added lines")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
