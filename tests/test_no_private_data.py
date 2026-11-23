"""Guard: no real contact data or Google OAuth client secrets in any tracked file.

The repo is public. Owner addresses and Google client IDs and secrets live only in
the tools' own credential stores (n8n, Make, Zapier), never in the repo or exports.
"""
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".mp4", ".mov", ".zip"}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
ALLOWED_EMAIL_DOMAINS = re.compile(r"@(?:[A-Za-z0-9-]+\.)*(example\.(com|org|net)|[A-Za-z0-9-]+\.example)$", re.I)
GOOGLE_CLIENT_ID = re.compile(r"\d{6,}-[a-z0-9]{20,}\.apps\.googleusercontent\.com")
GOOGLE_CLIENT_SECRET = re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}")


def tracked_text_files():
    """Every file git tracks or would add: tracked plus untracked, minus ignored."""
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    for rel in out.splitlines():
        path = REPO / rel
        if path.suffix.lower() in BINARY or not path.is_file():
            continue
        yield rel, path.read_text(encoding="utf-8", errors="ignore")


def test_no_real_email_addresses_in_tracked_files():
    found = []
    for rel, text in tracked_text_files():
        for m in EMAIL.finditer(text):
            if not ALLOWED_EMAIL_DOMAINS.search(m.group(0)):
                found.append(f"{rel}: {m.group(0)}")
    assert not found, "real-looking email addresses in tracked files:\n" + "\n".join(found)


def test_no_google_oauth_client_id_or_secret_in_tracked_files():
    found = []
    for rel, text in tracked_text_files():
        if GOOGLE_CLIENT_ID.search(text):
            found.append(f"{rel}: Google OAuth client ID")
        if GOOGLE_CLIENT_SECRET.search(text):
            found.append(f"{rel}: Google OAuth client secret")
    assert not found, "\n".join(found)


NON_SECRET_ENV_KEYS = {"HUBSPOT_BASE_URL", "HUBSPOT_APP_HOST", "HUBSPOT_PORTAL_ID", "N8N_BASE_URL"}


def test_no_local_env_value_appears_in_tracked_files():
    """Checks every value in the local .env (keys, tracker ID, webhook URLs). Skipped in CI, which has no .env."""
    env_path = REPO / ".env"
    if not env_path.exists():
        pytest.skip("no local .env")
    from dotenv import dotenv_values

    values = {k: v for k, v in dotenv_values(env_path).items() if v and len(v) >= 8 and k not in NON_SECRET_ENV_KEYS}
    found = [f"{rel}: value of {k}" for rel, text in tracked_text_files() for k, v in values.items() if v in text]
    assert not found, "\n".join(found)


def test_guard_patterns_catch_what_they_should():
    # Samples are built at run time so this file passes its own scan.
    at = "@"
    assert not ALLOWED_EMAIL_DOMAINS.search("someone" + at + "gmail.com")
    assert ALLOWED_EMAIL_DOMAINS.search("owner" + at + "example.com")
    assert ALLOWED_EMAIL_DOMAINS.search("sales" + at + "northwind-freight.example")
    assert GOOGLE_CLIENT_ID.search("1234567890" + "12-" + "abcdefghijklmnopqrstuvwxyz012345" + ".apps.googleusercontent.com")
    assert GOOGLE_CLIENT_SECRET.search("GOCSPX" + "-AbCdEfGhIjKlMnOp")
