"""Tests for scripts/prepush_check.py. Samples are built at run time so the guard test passes on this file."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import prepush_check as pc  # noqa: E402

AT = "@"
NOREPLY = "1234+someone" + AT + "users.noreply.github.com"
GMAIL = "someone" + AT + "gmail.com"


def test_identity_needs_noreply_for_author_and_committer():
    assert pc.check_identity("abc1234", NOREPLY, NOREPLY) == []
    found = pc.check_identity("abc1234", GMAIL, NOREPLY)
    assert found == ["abc1234: author email is not a GitHub no-reply address"]
    assert len(pc.check_identity("abc1234", GMAIL, GMAIL)) == 2


def test_message_rejects_agent_lines_but_allows_plain_mentions():
    assert pc.check_message("a", "Chapter 3: Claude key proved\n\nThe Code chat checked it.") == []
    assert pc.check_message("a", "Fix\n\nCo-Authored-By: Someone <x" + AT + "anthropic.com>")
    assert pc.check_message("a", "Fix\n\nGenerated with [Claude Code](https://claude.com/claude-code)")


def test_scan_added_finds_private_values_emails_and_google_secrets():
    files = {
        "a.md": ["tracker 1AbCdEfGhIjKlMnOpQrStUvWxYz", "owner" + AT + "example.com is fine"],
        "b.md": ["mail " + GMAIL],
        "c.md": ["GOCSPX" + "-AbCdEfGhIjKlMnOp"],
    }
    found = pc.scan_added(files, {".env SLICE_TRACKER_ID": "1AbCdEfGhIjKlMnOpQrStUvWxYz"})
    assert "a.md: holds a private value (.env SLICE_TRACKER_ID)" in found
    assert "b.md: holds a real-looking email address" in found
    assert "c.md: holds a Google OAuth client secret" in found
    assert not any(f.startswith("a.md: holds a real-looking") for f in found)


def test_added_lines_by_file_reads_only_added_lines():
    diff = "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1,2 @@\n-old\n+new line\n kept\n"
    assert pc.added_lines_by_file(diff) == {"x": ["new line"]}
