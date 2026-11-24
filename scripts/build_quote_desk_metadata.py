#!/usr/bin/env python3
"""Write the chapter 5 Salesforce metadata (salesforce/quote-desk/) from salesforce/quote-desk-setup.json.

Parts B to D of docs/v2/chapter-5-build.md as metadata instead of Setup clicks (COURSES 2ND's change
of method, 24/11/2026), so the org, the guide and the file stay one source:

  objects/Quote/fields/   the seven GTM fields on Quote (part B)
  profiles/Admin          field-level security for System Administrator on those fields only (part B).
                          A partial profile: a deploy changes only what the file lists
  profiles/GTM v2 API only  API Enabled and API Only User on the copied minimum-access profile (part C);
                          partial in the same way
  permissionsets/         "GTM v2 quote desk" (part D): Quote read and edit, Opportunity, Account and
                          Product read, field permissions as listed in the setup file; no licence
  layouts/                the org's Quote Layout with a "GTM v2 quote desk" section added (part B).
                          Only with --layout: the layout is the org's own, retrieved first

  python scripts/build_quote_desk_metadata.py [--layout <retrieved Quote-Quote Layout.layout-meta.xml>]
  python scripts/build_quote_desk_metadata.py --check

Deployed by the Code chat with the admin CLI login (sf project deploy start). Part E, the user,
is data, not metadata: scripts/make_desk_user.py. Exit codes: 0 done, 1 out of date, 2 could not build.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parents[1]
SETUP = json.loads((REPO / "salesforce" / "quote-desk-setup.json").read_text(encoding="utf-8"))
PROJECT = REPO / "salesforce" / "quote-desk"
SRC = PROJECT / "force-app" / "main" / "default"
API = SETUP["api_version"].lstrip("v")
NS = 'xmlns="http://soap.sforce.com/2006/04/metadata"'
SECTION_LABEL = "GTM v2 quote desk"
LAYOUT = SRC / "layouts" / "Quote-Quote Layout.layout-meta.xml"


def xml(root: str, body: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<{root} {NS}>\n{body}</{root}>\n'


def tag(name: str, value, indent: int = 4) -> str:
    v = str(value).lower() if isinstance(value, bool) else escape(str(value))
    return f"{' ' * indent}<{name}>{v}</{name}>\n"


def field_xml(f: dict) -> str:
    b = tag("fullName", f["api_name"])
    if f["setup_type"] == "Text":
        if f.get("external_id"):
            b += tag("caseSensitive", f.get("case_sensitive", False))
        b += tag("description", f["description"]) + tag("externalId", bool(f.get("external_id"))) + tag("label", f["label"])
        b += tag("length", f["length"]) + tag("required", False) + tag("trackHistory", False) + tag("type", "Text")
        b += tag("unique", bool(f.get("unique")))
    elif f["setup_type"] == "Number":
        b += tag("description", f["description"]) + tag("externalId", False) + tag("label", f["label"])
        b += tag("precision", f["setup_length"] + f["setup_decimal_places"]) + tag("required", False) + tag("scale", f["setup_decimal_places"])
        b += tag("trackHistory", False) + tag("type", "Number") + tag("unique", False)
    elif f["setup_type"] == "Text Area (Long)":
        b += tag("description", f["description"]) + tag("label", f["label"]) + tag("length", f["length"])
        b += tag("trackHistory", False) + tag("type", "LongTextArea") + tag("visibleLines", f["visible_lines"])
    else:
        raise ValueError(f"no metadata for field type {f['setup_type']}")
    return xml("CustomField", b)


def admin_profile_xml() -> str:
    b = "".join("    <fieldPermissions>\n" + tag("editable", True, 8) + tag("field", f"Quote.{f['api_name']}", 8) + tag("readable", True, 8)
                + "    </fieldPermissions>\n" for f in SETUP["custom_fields"])
    return xml("Profile", b)


def desk_profile_xml() -> str:
    b = tag("custom", True)
    for perm in SETUP["desk_profile"]["api_permissions"]:
        b += "    <userPermissions>\n" + tag("enabled", True, 8) + tag("name", perm, 8) + "    </userPermissions>\n"
    return xml("Profile", b)


OBJECT_FLAGS = {"Read": "allowRead", "Edit": "allowEdit", "Create": "allowCreate", "Delete": "allowDelete",
                "View All": "viewAllRecords", "Modify All": "modifyAllRecords"}


def permission_set_xml() -> str:
    ps = SETUP["permission_set"]
    b = tag("description", "Lets the GTM v2 quote desk read quotes and change only their status and the two desk fields. No create, no delete.")
    fields = []
    for obj, access in ps["field_permissions_api"].items():
        if obj == "about":
            continue
        for name in access.get("edit", []):
            fields.append((f"{obj}.{name}", True))
        for name in access.get("read", []):
            fields.append((f"{obj}.{name}", False))
    for name, edit in sorted(fields):
        b += "    <fieldPermissions>\n" + tag("editable", edit, 8) + tag("field", name, 8) + tag("readable", True, 8) + "    </fieldPermissions>\n"
    b += tag("hasActivationRequired", False) + tag("label", ps["label"])
    for obj in sorted(ps["object_permissions"]):
        allowed = set(ps["object_permissions"][obj])
        b += "    <objectPermissions>\n"
        for label, el in sorted(OBJECT_FLAGS.items(), key=lambda kv: kv[1]):
            b += tag(el, label in allowed, 8)
        b += tag("object", obj, 8) + "    </objectPermissions>\n"
    return xml("PermissionSet", b)


def section_xml() -> str:
    custom = [f["api_name"] for f in SETUP["custom_fields"] if f["api_name"] != "GTM_Case_Id__c"]
    left, right = custom[:3], custom[3:]

    def column(names):
        items = "".join("            <layoutItems>\n" + tag("behavior", "Edit", 16) + tag("field", n, 16) + "            </layoutItems>\n" for n in names)
        return f"        <layoutColumns>\n{items}        </layoutColumns>\n"

    return ("    <layoutSections>\n" + tag("customLabel", True, 8) + tag("detailHeading", True, 8) + tag("editHeading", True, 8)
            + tag("label", SECTION_LABEL, 8) + column(left) + column(right) + tag("style", "TwoColumnsTopToBottom", 8) + "    </layoutSections>\n")


def with_desk_section(layout: str) -> str:
    """The layout with the desk section after Quote Information, replacing any earlier copy of it."""
    layout = re.sub(r"    <layoutSections>\n(?:(?!    </layoutSections>).)*?<label>" + re.escape(SECTION_LABEL) + r"</label>.*?    </layoutSections>\n",
                    "", layout, flags=re.S)
    marker = "<label>Quote Information</label>"
    at = layout.find(marker)
    if at < 0:
        raise ValueError("the layout has no Quote Information section")
    end = layout.find("    </layoutSections>\n", at) + len("    </layoutSections>\n")
    return layout[:end] + section_xml() + layout[end:]


def files(layout_source: str | None) -> dict[Path, str]:
    out = {
        PROJECT / "sfdx-project.json": json.dumps({"name": "gtm-v2-quote-desk", "packageDirectories": [{"path": "force-app", "default": True}],
                                                   "sourceApiVersion": API}, indent=2) + "\n",
        SRC / "profiles" / "Admin.profile-meta.xml": admin_profile_xml(),
        SRC / "profiles" / f"{SETUP['desk_profile']['label']}.profile-meta.xml": desk_profile_xml(),
        SRC / "permissionsets" / f"{SETUP['permission_set']['api_name']}.permissionset-meta.xml": permission_set_xml(),
    }
    for f in SETUP["custom_fields"]:
        out[SRC / "objects" / "Quote" / "fields" / f"{f['api_name']}.field-meta.xml"] = field_xml(f)
    if layout_source is not None:
        out[LAYOUT] = with_desk_section(layout_source)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--layout", type=Path, help="the Quote Layout retrieved from the org, to add the desk section to")
    ap.add_argument("--check", action="store_true", help="exit 1 if any written file is out of date")
    args = ap.parse_args(argv)
    try:
        layout = args.layout.read_text(encoding="utf-8") if args.layout else (LAYOUT.read_text(encoding="utf-8") if LAYOUT.exists() else None)
        wanted = files(layout)
    except (OSError, ValueError, KeyError) as e:
        print(f"CANNOT BUILD {e}")
        return 2
    stale = [p for p, text in wanted.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    if args.check:
        for p in stale:
            print(f"OUT OF DATE {p.relative_to(REPO)}")
        print("The quote desk metadata is up to date." if not stale else "Run python scripts/build_quote_desk_metadata.py")
        return 1 if stale else 0
    for p, text in wanted.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    print(f"Wrote {len(wanted)} files under {PROJECT.relative_to(REPO)}" + ("" if layout is not None else " (no layout: pass --layout)") + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
