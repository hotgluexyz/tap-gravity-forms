"""GravityForms tap class."""

from __future__ import annotations

from typing import Any

import requests
from hotglue_singer_sdk import Stream, Tap
from hotglue_singer_sdk import typing as th
from requests.auth import HTTPBasicAuth
from typing_extensions import override

from tap_gravity_forms.streams import (
    FormEntriesStream,
    build_entries_schema,
    build_field_name_map,
    unique_snake_name,
)

_FORM_IDS_SCHEMA = th.CustomType(
    {
        "oneOf": [
            {"type": "string"},
            {
                "type": "array",
                "items": {"type": ["string", "integer"]},
            },
        ]
    }
)


def parse_form_ids(value: Any) -> list[str]:
    """Normalize ``form_ids`` from an array or comma-separated string."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, (list, tuple)):
        parts = value
    else:
        raise ValueError(
            "form_ids must be an array or a comma-separated string "
            f"(got {type(value).__name__})"
        )

    form_ids: list[str] = []
    for part in parts:
        form_id = str(part).strip()
        if form_id:
            form_ids.append(form_id)
    return form_ids


class TapGravityForms(Tap):
    """Singer tap for Gravity Forms entries, with one stream per configured form."""

    name = "tap-gravity-forms"

    config_jsonschema = th.PropertiesList(
        th.Property(
            "base_url",
            th.StringType,
            required=True,
            description="WordPress site URL hosting Gravity Forms (e.g. https://example.com)",
        ),
        th.Property(
            "consumer_key",
            th.StringType,
            required=True,
            description="Gravity Forms REST API consumer key",
        ),
        th.Property(
            "consumer_secret",
            th.StringType,
            required=True,
            description="Gravity Forms REST API consumer secret",
        ),
        th.Property(
            "form_ids",
            _FORM_IDS_SCHEMA,
            required=True,
            description=(
                "Gravity Forms form IDs to discover and sync. "
                "Accepts a JSON array (e.g. [\"15\", \"16\"]) or a comma-separated "
                "string (e.g. \"15,16\")."
            ),
        ),
        th.Property(
            "start_date",
            th.DateTimeType,
            description="Earliest entry date to sync",
            default="2000-01-01T00:00:00Z",
        ),
        th.Property(
            "page_size",
            th.IntegerType,
            description="Number of entries to request per page",
            default=100,
        ),
    ).to_dict()

    def _api_root(self) -> str:
        return f"{self.config['base_url'].rstrip('/')}/wp-json/gf/v2"

    def _auth(self) -> HTTPBasicAuth:
        return HTTPBasicAuth(
            username=self.config["consumer_key"],
            password=self.config["consumer_secret"],
        )

    def _fetch_form(self, form_id: str | int) -> dict[str, Any]:
        """Fetch form definition used to build the entries stream schema."""
        url = f"{self._api_root()}/forms/{form_id}"
        response = requests.get(
            url,
            headers={
                "Content-Type": "application/json",
                "User-Agent": self.config.get("user_agent", "Gravity Forms Tap"),
            },
            auth=self._auth(),
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _stream_name(form: dict[str, Any], form_id: str, used_names: set[str]) -> str:
        """Snake-case the form title for the stream name; disambiguate duplicates."""
        title = (form.get("title") or "").strip() or f"form_{form_id}"
        return unique_snake_name(title, used_names, form_id)

    @override
    def discover_streams(self) -> list[Stream]:
        """Build one FormEntries stream per configured form ID."""
        streams: list[Stream] = []
        used_names: set[str] = set()
        page_size = int(self.config.get("page_size") or 100)

        for form_id_str in parse_form_ids(self.config["form_ids"]):
            form = self._fetch_form(form_id_str)
            name = self._stream_name(form, form_id_str, used_names)
            used_names.add(name)

            field_name_map = build_field_name_map(form)
            stream = FormEntriesStream(
                tap=self,
                form_id=form_id_str,
                name=name,
                schema=build_entries_schema(form, field_name_map),
                field_name_map=field_name_map,
            )
            stream.page_size = page_size
            streams.append(stream)

        return streams


if __name__ == "__main__":
    TapGravityForms.cli()
