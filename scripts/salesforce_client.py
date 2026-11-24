"""A small Salesforce REST client for the chapter 4 and 5 checks.

It signs in with the client-credentials flow of an External Client App, the same login n8n uses,
so a check sees exactly what the workflow can see. Two logins, chosen with `login`:

  routing (chapter 4)  "GTM v2 routing (n8n)", run as GTM Integration: SALESFORCE_CLIENT_ID, SALESFORCE_CLIENT_SECRET
  desk (chapter 5)     "GTM v2 quote desk (n8n)", run as GTM Quote Desk: SALESFORCE_DESK_CLIENT_ID, SALESFORCE_DESK_CLIENT_SECRET

Both use SALESFORCE_DOMAIN, the org's My Domain host. The values come from .env and are never
printed. Only the chapter 5 setup check and the demo reset write, and only through the desk's
own narrow login (see scripts/salesforce_quote_desk_check.py and scripts/seed_quotes.py).

Errors name the step and Salesforce's error code, never a value from .env.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[1]
SETUP = json.loads((REPO / "salesforce" / "setup.json").read_text(encoding="utf-8"))
API_VERSION = SETUP["api_version"]
ENV_KEYS = SETUP["env_keys"]
LOGINS = {
    "routing": ("SALESFORCE_DOMAIN", "SALESFORCE_CLIENT_ID", "SALESFORCE_CLIENT_SECRET"),
    "desk": ("SALESFORCE_DOMAIN", "SALESFORCE_DESK_CLIENT_ID", "SALESFORCE_DESK_CLIENT_SECRET"),
}
HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.my\.salesforce\.com$")


class SalesforceError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


class ConfigError(RuntimeError):
    pass


def settings_from_env(env_path: Path = REPO / ".env", login: str = "routing") -> dict[str, str]:
    domain_key, id_key, secret_key = LOGINS[login]
    values = dotenv_values(env_path) if env_path.exists() else {}
    missing = [k for k in (domain_key, id_key, secret_key) if not (values.get(k) or "").strip()]
    if missing:
        raise ConfigError(f"not in .env yet: {', '.join(missing)}")
    host = values[domain_key].strip().removeprefix("https://").rstrip("/").lower()
    if not HOST_RE.match(host):
        raise ConfigError("SALESFORCE_DOMAIN must be the org's My Domain host, ending in .my.salesforce.com")
    return {"host": host, "client_id": values[id_key].strip(), "client_secret": values[secret_key].strip()}


def _error(resp: requests.Response, step: str) -> SalesforceError:
    code, message = None, f"HTTP {resp.status_code}"
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, list) and body and isinstance(body[0], dict):
        code, message = body[0].get("errorCode"), body[0].get("message", message)
    elif isinstance(body, dict):
        code = body.get("error") or body.get("errorCode")
        message = body.get("error_description") or body.get("message") or message
    return SalesforceError(f"{step}: {code + ': ' if code else ''}{message}"[:300], resp.status_code, code)


class SalesforceClient:
    def __init__(self, host: str, client_id: str, client_secret: str, session: requests.Session | None = None):
        self.host = host
        self._client_id = client_id
        self._client_secret = client_secret
        self.session = session or requests.Session()
        self._token: dict | None = None

    @classmethod
    def from_env(cls, env_path: Path = REPO / ".env", login: str = "routing") -> "SalesforceClient":
        return cls(**settings_from_env(env_path, login))

    def sign_in(self) -> dict:
        """Client-credentials token. Returns what the token says about itself, never the token."""
        resp = self.session.post(f"https://{self.host}/services/oauth2/token", timeout=30, data={
            "grant_type": "client_credentials", "client_id": self._client_id, "client_secret": self._client_secret})
        if resp.status_code != 200:
            raise _error(resp, "sign-in")
        self._token = resp.json()
        identity = self._token.get("id", "")
        return {"scope": self._token.get("scope", ""), "user_id": identity.rstrip("/").rsplit("/", 1)[-1] if identity else None,
                "token_type": self._token.get("token_type")}

    def identity(self) -> dict:
        """Who the token runs as, from Salesforce's identity URL. The token itself is never returned."""
        if self._token is None:
            self.sign_in()
        info = self.get(self._token["id"])
        return {k: info.get(k) for k in ("user_id", "username", "display_name", "active", "user_type")}

    def can_query(self, sobject: str) -> bool:
        """False when this login cannot see the object at all (Salesforce answers INVALID_TYPE)."""
        try:
            self.query(f"SELECT Id FROM {sobject} LIMIT 1")
            return True
        except SalesforceError as e:
            if e.code == "INVALID_TYPE":
                return False
            raise

    def get(self, path: str, ok_404: bool = False):
        if self._token is None:
            self.sign_in()
        url = path if path.startswith("https://") else f"https://{self.host}{path}"
        resp = self.session.get(url, timeout=30, headers={"Authorization": f"Bearer {self._token['access_token']}"})
        if resp.status_code == 404 and ok_404:
            return None
        if resp.status_code != 200:
            raise _error(resp, f"GET {path.split('?')[0]}")
        return resp.json()

    def data(self, path: str, ok_404: bool = False):
        return self.get(f"/services/data/{API_VERSION}{path}", ok_404=ok_404)

    def query(self, soql: str) -> list[dict]:
        return self.data(f"/query?q={quote(soql)}")["records"]

    def send(self, method: str, path: str, body: dict | list | None = None, ok_status: tuple = (200, 201, 204)):
        """A write, for the desk's own login only. Returns (status, body); raises with Salesforce's code otherwise."""
        if self._token is None:
            self.sign_in()
        url = f"https://{self.host}/services/data/{API_VERSION}{path}"
        resp = self.session.request(method, url, timeout=30, json=body,
                                    headers={"Authorization": f"Bearer {self._token['access_token']}", "Content-Type": "application/json"})
        if resp.status_code not in ok_status:
            raise _error(resp, f"{method} {path.split('?')[0]}")
        return resp.status_code, (resp.json() if resp.content else None)

    def account(self, record_id: str, fields: list[str]) -> dict | None:
        return self.data(f"/sobjects/Account/{quote(record_id)}?fields={','.join(fields)}", ok_404=True)

    def account_by_key(self, domain: str, fields: list[str]) -> dict | None:
        key = SETUP["external_id_field"]
        return self.data(f"/sobjects/Account/{key}/{quote(domain, safe='')}?fields={','.join(fields)}", ok_404=True)
