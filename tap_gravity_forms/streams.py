"""Stream type classes for tap-gravity-forms."""

from __future__ import annotations

import re
from typing import Any

from hotglue_singer_sdk import typing as th
from typing_extensions import override

from tap_gravity_forms.client import GravityFormsStream

# Entry metadata always present on Gravity Forms entry objects.
_ENTRY_META_PROPERTIES = [
    th.Property("id", th.StringType, description="Entry ID"),
    th.Property("form_id", th.StringType, description="Form ID"),
    th.Property("post_id", th.StringType, description="Associated WordPress post ID"),
    th.Property("date_created", th.DateTimeType, description="When the entry was created"),
    th.Property("date_updated", th.DateTimeType, description="When the entry was last updated"),
    th.Property("is_starred", th.StringType, description="Whether the entry is starred"),
    th.Property("is_read", th.StringType, description="Whether the entry has been read"),
    th.Property("ip", th.StringType, description="Submitter IP address"),
    th.Property("source_url", th.StringType, description="URL where the form was submitted"),
    th.Property("user_agent", th.StringType, description="Submitter user agent"),
    th.Property("currency", th.StringType, description="Payment currency"),
    th.Property("payment_status", th.StringType, description="Payment status"),
    th.Property("payment_date", th.DateTimeType, description="Payment date"),
    th.Property("payment_amount", th.StringType, description="Payment amount"),
    th.Property("payment_method", th.StringType, description="Payment method"),
    th.Property("transaction_id", th.StringType, description="Payment transaction ID"),
    th.Property("is_fulfilled", th.StringType, description="Whether payment is fulfilled"),
    th.Property("created_by", th.StringType, description="WordPress user ID that created the entry"),
    th.Property("transaction_type", th.StringType, description="Payment transaction type"),
    th.Property("status", th.StringType, description="Entry status (active, spam, trash)"),
    th.Property("source_id", th.StringType, description="Source ID"),
]

_ENTRY_META_KEYS = frozenset(prop.name for prop in _ENTRY_META_PROPERTIES)

# Field types that never store meaningful submission values (still mapped if present).
_DISPLAY_ONLY_TYPES = frozenset({"section", "html", "page", "captcha"})


def to_snake_case(value: str) -> str:
    """Normalize a label/title to a Singer-friendly snake_case identifier."""
    text = value.strip().lower().replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        return "field"
    if text[0].isdigit():
        text = f"field_{text}"
    return text


def unique_snake_name(base: str, used: set[str], fallback_id: str) -> str:
    """Return a unique snake_case name, appending the GF id on collision."""
    candidate = to_snake_case(base) if base else to_snake_case(f"field_{fallback_id}")
    if candidate not in used and candidate not in _ENTRY_META_KEYS:
        return candidate

    with_id = to_snake_case(f"{candidate}_{fallback_id}")
    if with_id not in used and with_id not in _ENTRY_META_KEYS:
        return with_id

    suffix = 2
    while True:
        numbered = f"{with_id}_{suffix}"
        if numbered not in used and numbered not in _ENTRY_META_KEYS:
            return numbered
        suffix += 1


def build_field_name_map(form: dict[str, Any]) -> dict[str, str]:
    """Map Gravity Forms field/input IDs to snake_case property names."""
    name_map: dict[str, str] = {}
    used_names: set[str] = set()

    for field in form.get("fields") or []:
        if not isinstance(field, dict) or field.get("id") is None:
            continue

        field_label = str(field.get("adminLabel") or field.get("label") or "")
        inputs = field.get("inputs")

        if isinstance(inputs, list) and inputs:
            for inp in inputs:
                if not isinstance(inp, dict) or inp.get("id") is None:
                    continue
                input_id = str(inp["id"])
                if input_id in name_map:
                    continue
                input_label = str(inp.get("customLabel") or inp.get("label") or "")
                base = input_label or field_label or f"field_{input_id}"
                name = unique_snake_name(base, used_names, input_id)
                used_names.add(name)
                name_map[input_id] = name
            continue

        field_id = str(field["id"])
        if field_id in name_map:
            continue
        base = field_label or f"field_{field_id}"
        name = unique_snake_name(base, used_names, field_id)
        used_names.add(name)
        name_map[field_id] = name

    return name_map


def build_entries_schema(
    form: dict[str, Any],
    field_name_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a Singer schema for entries using snake_case field names."""
    field_name_map = field_name_map or build_field_name_map(form)
    properties: list[th.Property] = list(_ENTRY_META_PROPERTIES)

    # Preserve form field order while naming from the map.
    seen: set[str] = set()
    for field in form.get("fields") or []:
        if not isinstance(field, dict) or field.get("id") is None:
            continue

        field_type = str(field.get("type") or field.get("inputType") or "")
        display_only = field.get("displayOnly") in (True, "1", 1)
        field_label = str(field.get("label") or field.get("adminLabel") or "")
        inputs = field.get("inputs")

        if isinstance(inputs, list) and inputs:
            for inp in inputs:
                if not isinstance(inp, dict) or inp.get("id") is None:
                    continue
                input_id = str(inp["id"])
                prop_name = field_name_map.get(input_id)
                if not prop_name or prop_name in seen:
                    continue
                seen.add(prop_name)
                input_label = str(inp.get("customLabel") or inp.get("label") or "")
                description = (
                    f"{field_label} - {input_label}" if input_label else field_label
                ) or input_id
                properties.append(
                    th.Property(prop_name, th.StringType, description=description)
                )
            continue

        field_id = str(field["id"])
        prop_name = field_name_map.get(field_id)
        if not prop_name or prop_name in seen:
            continue
        seen.add(prop_name)

        if display_only or field_type in _DISPLAY_ONLY_TYPES:
            description = field_label or f"{field_type} field {field_id}"
        else:
            description = field_label or field_id

        properties.append(
            th.Property(prop_name, th.StringType, description=description)
        )

    schema = th.PropertiesList(*properties).to_dict()
    schema["additionalProperties"] = True
    return schema


class FormEntriesStream(GravityFormsStream):
    """Entries (responses) for a single Gravity Forms form."""

    primary_keys = ["id"]
    replication_key = "date_updated"

    def __init__(
        self,
        tap,
        form_id: str | int,
        name: str,
        schema: dict[str, Any],
        field_name_map: dict[str, str] | None = None,
    ) -> None:
        self.form_id = str(form_id)
        self.field_name_map = field_name_map or {}
        super().__init__(
            tap=tap,
            name=name,
            schema=schema,
            path=f"/forms/{self.form_id}/entries",
        )

    @override
    def post_process(
        self,
        row: dict,
        context: dict | None = None,
    ) -> dict | None:
        """Remap GF field IDs to snake_case names and keep entry metadata."""
        row.setdefault("form_id", self.form_id)
        if not self.field_name_map:
            return row

        remapped = dict(row)
        for field_id, prop_name in self.field_name_map.items():
            if field_id in remapped:
                remapped[prop_name] = remapped.pop(field_id)
        return remapped
