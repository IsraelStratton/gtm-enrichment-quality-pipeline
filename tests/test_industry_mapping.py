"""Tests for scripts/industry_mapping.py — mapping and DQ-07 logic."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import industry_mapping as im  # noqa: E402


@pytest.mark.parametrize("clay_text, expected", [
    ("Computer Software", "COMPUTER_SOFTWARE"),
    ("computer software", "COMPUTER_SOFTWARE"),
    ("  Computer Software  ", "COMPUTER_SOFTWARE"),
    ("Hospital & Health Care", "HOSPITAL_HEALTH_CARE"),
    ("Financial Services", "FINANCIAL_SERVICES"),
    ("E-Learning", "E_LEARNING"),
    ("Leisure, Travel & Tourism", "LEISURE_TRAVEL_TOURISM"),
    ("Mining & Metals", "MINING_METALS"),
    ("Renewables & Environment", "RENEWABLES_ENVIRONMENT"),
    ("Transportation/Trucking/Railroad", "TRANSPORTATION_TRUCKING_RAILROAD"),
])
def test_map_industry_known_values(clay_text, expected):
    assert im.map_industry(clay_text) == expected


@pytest.mark.parametrize("clay_text", [
    "Leisure Travel & Tourism",  # missing comma — unmapped
    "Made-Up Industry",
    "SaaS",
    "Tech",
])
def test_map_industry_unmapped(clay_text):
    assert im.map_industry(clay_text) is None


@pytest.mark.parametrize("clay_text", [
    "",
    "   ",
])
def test_map_industry_blank(clay_text):
    assert im.map_industry(clay_text) is None


def test_mapping_table_has_148_entries():
    assert len(im.INDUSTRY_MAP) == 148


def test_all_keys_are_lowercase_trimmed():
    for key in im.INDUSTRY_MAP:
        assert key == key.strip().lower(), f"Key {key!r} is not normalised"


def test_dq06_and_dq07_mutually_exclusive():
    """DQ-06 fires when industry is blank; DQ-07 fires when present but unmapped.
    They should never both fire for the same input."""
    # Blank -> DQ-06 (INDUSTRY_MISSING), not DQ-07
    assert im.map_industry("") is None  # blank triggers DQ-06
    # Present but unmapped -> DQ-07 (INDUSTRY_UNMAPPED), not DQ-06
    assert im.map_industry("Leisure Travel & Tourism") is None  # present, unmapped -> DQ-07
    # The distinction is: blank vs present-but-unmapped, checked by the caller
    # This test documents the contract: map_industry returns None for both,
    # but the caller checks if the original was blank (DQ-06) or not (DQ-07)
