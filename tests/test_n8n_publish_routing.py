"""scripts/n8n_publish_routing.py: credentials matched by name and type, and the drift check
that compares a live workflow with its file. No network."""
import copy
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_n8n_routing as build  # noqa: E402
import n8n_publish_routing as pub  # noqa: E402

CREDS = [
    {"id": "c1", "type": "httpHeaderAuth", "name": "Claude key gtm-pipeline-v2"},
    {"id": "c2", "type": "postgres", "name": "GTM v2 run log (Postgres)"},
    {"id": "c3", "type": "httpHeaderAuth", "name": "HubSpot Service Key"},
    {"id": "c4", "type": "oAuth2Api", "name": "Salesforce gtm-pipeline (client credentials)"},
]


def test_credentials_are_filled_in_by_name_and_type():
    wf = pub.with_credential_ids(build.build("salesforce"), CREDS)
    ids = {n["name"]: next(iter(n["credentials"].values()))["id"] for n in wf["nodes"] if n.get("credentials")}
    assert ids["Salesforce Upsert"] == "c4" and ids["Claude Routing Step"] == "c1" and ids["Log Decisions"] == "c2"
    assert all(next(iter(n["credentials"].values()))["id"] is None for n in build.build("salesforce")["nodes"] if n.get("credentials"))


def test_a_missing_credential_stops_the_import_and_is_named():
    with pytest.raises(LookupError, match="Salesforce gtm-pipeline \\(client credentials\\)' \\(oAuth2Api\\)"):
        pub.with_credential_ids(build.build("salesforce"), CREDS[:3])
    same_name_wrong_type = CREDS[:3] + [{"id": "c9", "type": "salesforceOAuth2Api", "name": "Salesforce gtm-pipeline (client credentials)"}]
    with pytest.raises(LookupError):
        pub.with_credential_ids(build.build("salesforce"), same_name_wrong_type)


def as_n8n_holds_it(wf):
    """What n8n gives back: IDs and positions of its own, and defaults left out."""
    live = copy.deepcopy(wf)
    for n in live["nodes"]:
        n["id"], n["position"] = "x", [0, 0]
        if n["name"] == "Loop Over Leads":
            n["parameters"].pop("batchSize")  # n8n drops a parameter equal to its default
        for cred in (n.get("credentials") or {}).values():
            cred["id"] = "live-id"
    live["settings"] = dict(live["settings"], binaryMode="separate")
    return live


def test_a_live_copy_n8n_has_normalised_is_in_step():
    wf = build.build("hubspot")
    assert pub.differences(as_n8n_holds_it(wf), wf) == []


@pytest.mark.parametrize("change, words", [
    (lambda w: next(n for n in w["nodes"] if n["name"] == "Apply Decisions")["parameters"].update(jsCode="return [];"), "Apply Decisions"),
    (lambda w: next(n for n in w["nodes"] if n["name"] == "HubSpot Batch Upsert")["parameters"].update(url="https://evil.example/"), "HubSpot Batch Upsert: parameters"),
    (lambda w: next(n for n in w["nodes"] if n["name"] == "Claude Routing Step").update(retryOnFail=False), "Claude Routing Step: retryOnFail"),
    (lambda w: w["nodes"].append({"name": "Send Email", "type": "n8n-nodes-base.emailSend", "parameters": {}}), "Send Email: in n8n but not in the file"),
    (lambda w: w["connections"].pop("Review Page"), "the connections"),
])
def test_a_live_copy_that_was_changed_by_hand_is_out_of_step(change, words):
    wf = build.build("hubspot")
    live = as_n8n_holds_it(wf)
    change(live)
    assert any(words in d for d in pub.differences(live, wf)), pub.differences(live, wf)
