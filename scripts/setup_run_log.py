#!/usr/bin/env python3
"""Create or update the chapter 2 run log in the local Supabase Postgres, then prove its limits.

  1. Applies db/run_log.sql as the database owner (inside the Supabase db container).
  2. Creates the login gtm_v2_pipeline. Its password is made here, written to .env as
     GTM_V2_DB_PASSWORD and never printed. Israel pastes it into the n8n Postgres credential.
  3. Grants that login the two add-only functions and the views, nothing else.
  4. Loads pricing/claude_prices.json into gtm_v2.model_prices.
  5. Signs in as gtm_v2_pipeline and checks what it can and cannot do.

  python scripts/setup_run_log.py            # all five steps
  python scripts/setup_run_log.py --check    # step 5 only

Exit codes: 0 done and every check passed, 1 a check failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

REPO = Path(__file__).resolve().parents[1]
ENV = REPO / ".env"
SQL = REPO / "db" / "run_log.sql"
PRICES = REPO / "pricing" / "claude_prices.json"
ROLE = "gtm_v2_pipeline"
PASSWORD_KEY = "GTM_V2_DB_PASSWORD"


def db_settings() -> dict[str, str]:
    """Where the pipeline login connects from the Mac. n8n uses host.docker.internal instead."""
    return {
        "container": os.environ.get("SUPABASE_DB_CONTAINER", "supabase_db_hubspot-ai-database"),
        "host": os.environ.get("GTM_V2_DB_HOST", "127.0.0.1"),
        "port": os.environ.get("GTM_V2_DB_PORT", "54322"),
        "dbname": os.environ.get("GTM_V2_DB_NAME", "postgres"),
        "user": ROLE,
    }


def ensure_password() -> str:
    """Return the pipeline password from .env, making and saving one if there is none."""
    current = (dotenv_values(ENV).get(PASSWORD_KEY) if ENV.exists() else None) or ""
    if current:
        return current
    password = secrets.token_urlsafe(24)  # letters, digits, - and _ only: safe inside a SQL literal
    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    if PASSWORD_KEY in text:
        lines = [f"{PASSWORD_KEY}={password}" if line.startswith(f"{PASSWORD_KEY}=") else line for line in text.splitlines()]
        text = "\n".join(lines) + "\n"
    else:
        text += ("" if text.endswith("\n") or not text else "\n")
        text += f"\n# Chapter 2 run log: the gtm_v2_pipeline login (made by scripts/setup_run_log.py). Paste into the n8n Postgres credential.\n{PASSWORD_KEY}={password}\n"
    ENV.write_text(text, encoding="utf-8")
    return password


def psql(container: str, sql: str) -> str:
    """Run SQL as the owner inside the db container. The SQL goes in on stdin, so no secret is on a command line."""
    out = subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-q", "-At"],
        input=sql, capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip().replace(os.environ.get(PASSWORD_KEY, "\0"), "<hidden>") or "psql failed")
    return out.stdout


def role_sql(password: str) -> str:
    if not password.replace("-", "").replace("_", "").isalnum():
        raise ValueError("the pipeline password must be letters, digits, - and _ only")
    return f"""
do $$
begin
  if not exists (select 1 from pg_roles where rolname = '{ROLE}') then
    create role {ROLE} login password '{password}' connection limit 5;
  else
    alter role {ROLE} login password '{password}' connection limit 5;
  end if;
end $$;
alter role {ROLE} set search_path = gtm_v2;
grant usage on schema gtm_v2 to {ROLE};
grant execute on function gtm_v2.log_proposals(jsonb), gtm_v2.log_decisions(jsonb) to {ROLE};
grant select on gtm_v2.decision_record, gtm_v2.run_summary, gtm_v2.cost_by_route to {ROLE};
"""


def prices_sql(prices: dict) -> str:
    def lit(v):
        if v is None:
            return "null"
        if isinstance(v, (int, float)):
            return repr(v)
        return "'" + str(v).replace("'", "''") + "'"

    rows = []
    for model, p in prices["models"].items():
        rows.append("(" + ", ".join(lit(x) for x in (
            model, p["input"], p["output"], p["long_prompt_over_tokens"], p["long_input"], p["long_output"], p["read_on"], p["source"],
        )) + ")")
    return (
        "insert into gtm_v2.model_prices (model, input_per_mtok, output_per_mtok, long_prompt_over_tokens, "
        "long_input_per_mtok, long_output_per_mtok, read_on, source) values\n  " + ",\n  ".join(rows) + "\n"
        "on conflict (model) do update set input_per_mtok = excluded.input_per_mtok, output_per_mtok = excluded.output_per_mtok, "
        "long_prompt_over_tokens = excluded.long_prompt_over_tokens, long_input_per_mtok = excluded.long_input_per_mtok, "
        "long_output_per_mtok = excluded.long_output_per_mtok, read_on = excluded.read_on, source = excluded.source;\n"
    )


def connect(settings: dict[str, str], password: str):
    import psycopg

    return psycopg.connect(host=settings["host"], port=settings["port"], dbname=settings["dbname"],
                           user=settings["user"], password=password, connect_timeout=5, autocommit=True)


def check_limits(settings: dict[str, str], password: str) -> list[tuple[str, bool]]:
    """What the pipeline login can and cannot do. Each check is (description, passed)."""
    import psycopg

    results = []

    def expect_denied(conn, label, sql):
        try:
            conn.execute(sql)
            results.append((label, False))
        except psycopg.errors.InsufficientPrivilege:
            results.append((label, True))

    with connect(settings, password) as conn:
        conn.execute("select count(*) from gtm_v2.run_summary").fetchone()
        results.append(("can read the run summary view", True))
        conn.execute("select gtm_v2.log_proposals('[]'::jsonb)").fetchone()
        results.append(("can call log_proposals", True))
        expect_denied(conn, "cannot read the proposals table directly", "select 1 from gtm_v2.proposals limit 1")
        expect_denied(conn, "cannot insert into proposals directly", "insert into gtm_v2.proposals (decision_id) values ('x')")
        expect_denied(conn, "cannot update decisions", "update gtm_v2.decisions set approver = 'x'")
        expect_denied(conn, "cannot delete proposals", "delete from gtm_v2.proposals")
        expect_denied(conn, "cannot change prices", "update gtm_v2.model_prices set input_per_mtok = 0")
        # pg_tables lists every table whatever the login may read (information_schema would hide them).
        for schema in ("ec", "public"):
            other = conn.execute(
                "select quote_ident(schemaname) || '.' || quote_ident(tablename) from pg_tables "
                "where schemaname = %s order by tablename limit 1", (schema,)
            ).fetchone()
            if other:
                expect_denied(conn, f"cannot read the {schema} schema ({other[0]})", f"select 1 from {other[0]} limit 1")
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="only sign in as the pipeline login and check its limits")
    args = ap.parse_args(argv)
    load_dotenv(ENV)
    settings = db_settings()
    try:
        password = ensure_password()
        os.environ[PASSWORD_KEY] = password
        if not args.check:
            psql(settings["container"], SQL.read_text(encoding="utf-8"))
            print("Applied db/run_log.sql (schema gtm_v2: proposals, decisions, model_prices, three views).")
            psql(settings["container"], role_sql(password))
            print(f"Login {ROLE} ready: two add-only functions and three views. Password is in .env as {PASSWORD_KEY}.")
            prices = json.loads(PRICES.read_text(encoding="utf-8"))
            psql(settings["container"], prices_sql(prices))
            print(f"Loaded {len(prices['models'])} model prices from pricing/claude_prices.json.")
        results = check_limits(settings, password)
    except (RuntimeError, OSError, ValueError) as e:
        print(f"CANNOT RUN {e}")
        return 2
    except Exception as e:  # psycopg connection errors
        print(f"CANNOT RUN {type(e).__name__}: {str(e).replace(os.environ.get(PASSWORD_KEY, chr(0)), '<hidden>')}")
        return 2
    for label, ok in results:
        print(f"{'PASS' if ok else 'FAIL'} {ROLE} {label}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
