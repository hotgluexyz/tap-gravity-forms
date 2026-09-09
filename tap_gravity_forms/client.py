"""HTTP API client and GravityFormsStream base class."""

from __future__ import annotations

import json
from typing import Any

import requests
from hotglue_singer_sdk.authenticators import BasicAuthenticator
from hotglue_singer_sdk.streams import RESTStream
from typing_extensions import override


class GravityFormsStream(RESTStream):
    """Gravity Forms REST API stream base class."""

    records_jsonpath = "$.entries[*]"
    next_page_token_jsonpath = None
    page_size = 100

    @override
    @property
    def url_base(self) -> str:
        """Return the GF REST API root from the WordPress ``base_url`` setting."""
        base = self.config["base_url"].rstrip("/")
        return f"{base}/wp-json/gf/v2"

    @override
    @property
    def authenticator(self) -> BasicAuthenticator:
        """Return Basic Auth using Gravity Forms consumer key/secret."""
        return BasicAuthenticator.create_for_stream(
            self,
            username=self.config["consumer_key"],
            password=self.config["consumer_secret"],
        )

    @override
    @property
    def http_headers(self) -> dict:
        """Return HTTP headers for Gravity Forms API requests."""
        return {"Content-Type": "application/json"}

    @override
    def get_next_page_token(
        self,
        response: requests.Response,
        previous_token: Any | None,
    ) -> Any | None:
        """Advance ``paging[current_page]`` until all entries are consumed."""
        data = response.json()
        current_page = 1 if previous_token is None else int(previous_token)
        total_count = int(data.get("total_count") or 0)
        if current_page * self.page_size >= total_count:
            return None
        return current_page + 1

    @override
    def get_url_params(
        self,
        context: dict | None,
        next_page_token: Any | None,
    ) -> dict[str, Any]:
        """Return paging, sorting, and optional incremental search params."""
        params: dict[str, Any] = {
            "paging[page_size]": self.page_size,
            "paging[current_page]": int(next_page_token or 1),
            "sorting[key]": self.replication_key or "id",
            "sorting[direction]": "ASC",
        }

        starting_replication_value = self.get_starting_replication_key_value(context)
        if starting_replication_value and self.replication_key:
            # Prefer filtering on the replication key; fall back to start_date for
            # date_created bookmarks (native Gravity Forms search argument).
            bookmark = str(starting_replication_value)[:19]
            if self.replication_key == "date_created":
                params["search"] = json.dumps({"start_date": bookmark})
            else:
                params["search"] = json.dumps(
                    {
                        "field_filters": [
                            {
                                "key": self.replication_key,
                                "value": bookmark,
                                "operator": ">=",
                            }
                        ]
                    }
                )

        return params
