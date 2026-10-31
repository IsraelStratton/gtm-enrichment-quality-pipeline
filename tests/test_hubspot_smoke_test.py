"""Tests for scripts/hubspot_smoke_test.py. All HubSpot I/O is faked; no network."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hubspot_smoke_test as hs  # noqa: E402

TOKEN = "pat-fake-token-do-not-print"
DOMAIN = "gtm-pipeline-smoke-test.example"


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.content = b"" if body is None else json.dumps(body).encode()
        self.text = self.content.decode()

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


class FakeSession:
    """Returns queued responses in order and records every call."""

    def __init__(self, responses):
        self.headers = {}
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, json=None, timeout=None):
        self.calls.append((method, url, json))
        return self.responses.pop(0)


def make_client(responses):
    session = FakeSession(responses)
    return hs.HubSpotClient(TOKEN, session=session, sleep=lambda s: None), session


def found(*ids):
    return FakeResponse(body={"results": [{"id": i} for i in ids]})


def stored(description, domain=DOMAIN):
    return FakeResponse(body={"id": "101", "properties": {"domain": domain, "description": description}})


@pytest.mark.parametrize("raw, expected", [
    ("example.com", "example.com"),
    ("  Example.COM  ", "example.com"),
    ("https://www.Brightwater-Analytics.example/about", "brightwater-analytics.example"),
    ("http://acme.example:8080/path?q=1#x", "acme.example"),
    ("WWW.northwind-freight.example.", "northwind-freight.example"),
])
def test_normalise_domain(raw, expected):
    assert hs.normalise_domain(raw) == expected


@pytest.mark.parametrize("domain, valid", [
    ("northwind-freight.example", True),
    ("sub.domain.co.uk", True),
    ("not a domain", False),
    ("bad_domain.example", False),
    ("-bluegum.example", False),
    ("trailing-.example", False),
    ("localhost", False),
    ("example.c0m", False),
    ("", False),
    ("a" * 64 + ".example", False),
])
def test_is_valid_domain(domain, valid):
    assert hs.is_valid_domain(domain) is valid


def test_auth_header_set_and_token_kept_out_of_url():
    client, session = make_client([found()])
    client.search_by_domain(DOMAIN)
    assert session.headers["Authorization"] == f"Bearer {TOKEN}"
    method, url, body = session.calls[0]
    assert (method, url) == ("POST", "https://api.hubapi.com/crm/v3/objects/companies/search")
    assert TOKEN not in url
    assert body["filterGroups"][0]["filters"][0] == {"propertyName": "domain", "operator": "EQ", "value": DOMAIN}


def test_create_path_waits_for_search_then_updates():
    client, session = make_client([
        found(),                                  # upsert search: absent
        FakeResponse(201, {"id": "101"}),          # create
        found(),                                  # poll 1: not indexed yet
        found("101"),                             # poll 2: indexed
        found("101"),                             # second upsert search
        FakeResponse(200, {"id": "101"}),          # update
        stored("gtm-pipeline smoke test T (update)"),
    ])
    out = []
    assert hs.run_smoke_test(client, DOMAIN, "Co", stamp="T", out=out.append, sleep=lambda s: None) == 0
    methods = [(m, u.rsplit("/crm/v3/objects/companies", 1)[1]) for m, u, _ in session.calls]
    assert ("POST", "") in methods and ("PATCH", "/101") in methods
    create_body = session.calls[1][2]
    assert create_body["properties"]["domain"] == DOMAIN
    assert out[-1].startswith("PASS")
    assert any("Searchable after ~2s" in line for line in out)


def test_existing_company_takes_update_path_only():
    client, session = make_client([
        found("555"),
        FakeResponse(200, {"id": "555"}),
        stored("gtm-pipeline smoke test T (create/first)"),
    ])
    out = []
    assert hs.run_smoke_test(client, DOMAIN, "Co", stamp="T", out=out.append) == 0
    assert [c[0] for c in session.calls] == ["POST", "PATCH", "GET"]
    assert session.calls[1][1].endswith("/companies/555")


def test_ambiguous_domain_writes_nothing():
    client, session = make_client([found("1", "2")])
    out = []
    assert hs.run_smoke_test(client, DOMAIN, "Co", stamp="T", out=out.append) == 1
    assert len(session.calls) == 1
    assert "2 companies share domain" in out[-1]


def test_search_lag_timeout_fails_with_explanation():
    client, _ = make_client([found(), FakeResponse(201, {"id": "101"})] + [found()] * 16)
    out = []
    assert hs.run_smoke_test(client, DOMAIN, "Co", stamp="T", out=out.append, sleep=lambda s: None) == 1
    assert "not searchable after 30s" in out[-1]


def test_read_back_mismatch_fails():
    client, _ = make_client([found("555"), FakeResponse(200, {"id": "555"}), stored("something else")])
    out = []
    assert hs.run_smoke_test(client, DOMAIN, "Co", stamp="T", out=out.append) == 1
    assert "read-back mismatch" in out[-1]


def test_search_only_makes_one_read_call():
    client, session = make_client([found("9")])
    out = []
    assert hs.run_smoke_test(client, DOMAIN, "Co", search_only=True, out=out.append) == 0
    assert len(session.calls) == 1 and "1 match(es)" in out[-1]


def test_archive_deletes_test_company():
    client, session = make_client([
        found("555"), FakeResponse(200, {"id": "555"}),
        stored("gtm-pipeline smoke test T (create/first)"), FakeResponse(204),
    ])
    assert hs.run_smoke_test(client, DOMAIN, "Co", stamp="T", archive=True, out=lambda s: None) == 0
    assert session.calls[-1][0] == "DELETE"


@pytest.mark.parametrize("status, phrase", [(401, "Service key rejected"), (403, "Missing scope")])
def test_auth_errors_are_explained(status, phrase):
    client, _ = make_client([FakeResponse(status, {"message": "nope"})])
    with pytest.raises(hs.HubSpotError, match=phrase):
        client.search_by_domain(DOMAIN)


def test_retries_429_honouring_retry_after():
    slept = []
    session = FakeSession([FakeResponse(429, {"message": "slow down"}, {"Retry-After": "2"}), found()])
    client = hs.HubSpotClient(TOKEN, session=session, sleep=slept.append)
    assert client.search_by_domain(DOMAIN) == []
    assert slept == [2.0]


def test_gives_up_after_max_retries():
    session = FakeSession([FakeResponse(503, {"message": "down"})] * 4)
    client = hs.HubSpotClient(TOKEN, session=session, sleep=lambda s: None, max_retries=3)
    with pytest.raises(hs.HubSpotError, match="HTTP 503: down"):
        client.search_by_domain(DOMAIN)
    assert len(session.calls) == 4


def test_main_without_key_is_config_error(monkeypatch, capsys):
    monkeypatch.setattr(hs, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("HUBSPOT_SERVICE_KEY", raising=False)
    assert hs.main([]) == 2
    assert "HUBSPOT_SERVICE_KEY is not set" in capsys.readouterr().err


def test_main_rejects_invalid_domain(monkeypatch):
    monkeypatch.setattr(hs, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("HUBSPOT_SERVICE_KEY", TOKEN)
    assert hs.main(["--domain", "bad_domain.example"]) == 2


def test_main_never_prints_token(monkeypatch, capsys):
    monkeypatch.setattr(hs, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("HUBSPOT_SERVICE_KEY", TOKEN)
    monkeypatch.setenv("HUBSPOT_PORTAL_ID", "123")
    fake = FakeSession([found("555"), FakeResponse(200, {"id": "555"}), FakeResponse(401, {"message": "x"})])
    monkeypatch.setattr(hs.requests, "Session", lambda: fake)
    assert hs.main([]) == 1
    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err
