# tap-gravity-forms

A [Singer](https://www.singer.io/) tap that extracts **form entries** from [Gravity Forms](https://www.gravityforms.com/) on WordPress. It is built with [hotglue-singer-sdk](https://github.com/hotgluexyz/HotglueSingerSDK) and speaks the standard Singer message protocol on stdout.

## Features

- **Dynamic base URL** — each WordPress site hosts its own Gravity Forms REST API.
- **Dynamic catalog** — discover builds one stream per form in `form_ids`, named after the form title, with a schema derived from that form’s fields.
- **Basic Auth** via Gravity Forms REST API consumer key / secret.
- **Incremental sync** on `date_updated` (bookmark), with optional `start_date`.

### Streams

Streams are not fixed. On `--discover`, the tap calls `GET /wp-json/gf/v2/forms/{form_id}` for each ID in `form_ids` and emits a catalog entry whose:

| Aspect | Behavior |
| ------ | -------- |
| Stream name | Snake-cased form `title` (e.g. `advanced_contact_form`) |
| Schema | Entry metadata + one snake-cased property per form field / input label |
| Sync path | `GET /wp-json/gf/v2/forms/{form_id}/entries` |
| Primary key | `id` |
| Replication key | `date_updated` |

Pagination uses `paging[page_size]` / `paging[current_page]` until `total_count` is exhausted.

## Requirements

- Python **3.10+** (see `requires-python` in `pyproject.toml`).
- Gravity Forms REST API enabled on the WordPress site, with a consumer key/secret that can view entries.

## Installation

1. **Clone** this repository and `cd` into the project directory.
2. **Create `config.json`** with your credentials and settings (see [Configuration](#configuration)).
3. **Create a virtual environment** and activate it:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows, use `.venv\Scripts\activate` instead of `source .venv/bin/activate`.

4. **Install the package** in editable mode:

```bash
pip install -e .
```

5. **Run the tap** (with the venv still activated):

```bash
tap-gravity-forms --help
```

## Configuration

| Setting | Type | Required | Default | Description |
| ------- | ---- | -------- | ------- | ----------- |
| `base_url` | string | yes | — | WordPress site URL (e.g. `https://example.com`). |
| `consumer_key` | string | yes | — | Gravity Forms REST API consumer key (sensitive). |
| `consumer_secret` | string | yes | — | Gravity Forms REST API consumer secret (sensitive). |
| `form_ids` | array of string **or** comma-separated string | yes | — | Form IDs whose entries should be discovered and synced. |
| `start_date` | string (datetime) | no | `2000-01-01T00:00:00Z` | Earliest entry date to sync. |
| `page_size` | integer | no | `100` | Entries per API page. |

Run `tap-gravity-forms --about` (or `tap-gravity-forms --about --format=markdown`) for the authoritative schema for your installed version.

### Example `config.json`

```json
{
  "base_url": "https://example.com",
  "consumer_key": "ck_YOUR_CONSUMER_KEY",
  "consumer_secret": "cs_YOUR_CONSUMER_SECRET",
  "form_ids": ["15"],
  "start_date": "2000-01-01T00:00:00Z",
  "page_size": 100
}
```

`form_ids` also accepts a comma-separated string, e.g. `"15,16"`.

Do not commit real credentials. Prefer environment variables or a secrets manager in production.

### Environment-based config

You can load settings from the process environment using `--config=ENV` (the SDK merges env into config). Env names follow the tap’s setting keys (see `tap-gravity-forms --about`).

## Usage

With your virtual environment **activated** and `config.json` in place:

Discover stream catalog:

```bash
tap-gravity-forms --config config.json --discover > catalog.json
```

Run a sync (with optional state):

```bash
tap-gravity-forms --config config.json --catalog catalog.json --state state.json
```

Pipe to any Singer target:

```bash
tap-gravity-forms --config config.json --catalog catalog.json | target-jsonl
```

Inspect built-in settings and stream metadata:

```bash
tap-gravity-forms --about
```

## API / documentation

- API root: `{base_url}/wp-json/gf/v2`
- Form definition: [Getting Forms with the REST API](https://docs.gravityforms.com/getting-forms-with-the-rest-api-v2/)
- Entries: [Searching and Getting Entries](https://docs.gravityforms.com/searching-and-getting-entries-with-the-rest-api-v2/)
- Auth: Gravity Forms REST API consumer key / secret (HTTP Basic)

## License
MIT — see `LICENSE` and `pyproject.toml`.
