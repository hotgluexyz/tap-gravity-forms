"""Tests standard tap features using the built-in SDK tests library."""

import datetime

import pytest
from hotglue_singer_sdk.testing import get_standard_tap_tests

from tap_gravity_forms.streams import (
    build_entries_schema,
    build_field_name_map,
    to_snake_case,
)
from tap_gravity_forms.tap import TapGravityForms, parse_form_ids

SAMPLE_CONFIG = {
    "start_date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
    "base_url": "https://example.com",
    "consumer_key": "ck_placeholder",
    "consumer_secret": "cs_placeholder",
    "form_ids": ["15"],
}

# Discovery and connection tests need a live Gravity Forms API; exclude by default.
_EXCLUDED = {"_test_stream_connections", "_test_discovery"}
_STANDARD_TESTS = [
    t
    for t in get_standard_tap_tests(TapGravityForms, config=SAMPLE_CONFIG)
    if getattr(t, "__name__", "") not in _EXCLUDED
]


@pytest.mark.parametrize("test_func", _STANDARD_TESTS)
def test_standard(test_func):
    """Run built-in SDK tap tests (CLI output)."""
    test_func()


def test_to_snake_case():
    assert to_snake_case("Advanced Contact Form") == "advanced_contact_form"
    assert to_snake_case("Preferred Method of Contact") == "preferred_method_of_contact"
    assert to_snake_case("Your Name - First") == "your_name_first"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (["15", "16"], ["15", "16"]),
        ([15, 16], ["15", "16"]),
        ("15,16", ["15", "16"]),
        ("15, 16, 17", ["15", "16", "17"]),
        ("15", ["15"]),
        ("", []),
        ([], []),
    ],
)
def test_parse_form_ids(raw, expected):
    assert parse_form_ids(raw) == expected


def test_build_entries_schema_from_form_fields():
    """Schema uses snake_case labels mapped from GF field/input IDs."""
    form = {
        "id": 15,
        "title": "Advanced Contact Form",
        "fields": [
            {
                "id": 7,
                "type": "section",
                "displayOnly": "1",
                "label": "About You",
            },
            {
                "id": 1,
                "type": "name",
                "label": "Your Name",
                "inputs": [
                    {"id": "1.3", "label": "First"},
                    {"id": "1.6", "label": "Last"},
                ],
            },
            {
                "id": 11,
                "type": "select",
                "label": "Preferred Method of Contact",
                "inputs": "",
            },
            {
                "id": 20,
                "type": "checkbox",
                "label": "Interests",
                "inputs": [
                    {"id": "20.1", "label": "Pet Lover"},
                    {"id": "20.2", "label": "Gardening"},
                ],
            },
        ],
    }

    field_name_map = build_field_name_map(form)
    assert field_name_map["1.3"] == "first"
    assert field_name_map["1.6"] == "last"
    assert field_name_map["11"] == "preferred_method_of_contact"
    assert field_name_map["7"] == "about_you"
    assert field_name_map["20.1"] == "pet_lover"
    assert field_name_map["20.2"] == "gardening"

    schema = build_entries_schema(form, field_name_map)
    schema_properties = schema["properties"]

    assert "id" in schema_properties
    assert "date_updated" in schema_properties
    assert "first" in schema_properties
    assert "last" in schema_properties
    assert "preferred_method_of_contact" in schema_properties
    assert "about_you" in schema_properties
    assert "1.3" not in schema_properties
    assert schema.get("additionalProperties") is True

    assert schema_properties["pet_lover"]["field_meta"] == {"type": "checkbox"}
    assert schema_properties["gardening"]["field_meta"] == {"type": "checkbox"}
    assert "field_meta" not in schema_properties["first"]
    assert "field_meta" not in schema_properties["last"]
    assert "field_meta" not in schema_properties["preferred_method_of_contact"]
