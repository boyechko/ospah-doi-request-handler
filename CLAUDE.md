# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-file Python CLI that converts `.eml` files (DOI request form emails) into DataCite Kernel-4 XML for import into DataCite Fabrica. All logic lives in `src/main.py`.

## Running the tool

The `doi-request-handler` wrapper script delegates to `src/main.py` via `uv run`, which syncs `.venv/` from `uv.lock` on every invocation:

```bash
./doi-request-handler data/request.eml
```

Or directly:

```bash
uv run python src/main.py data/request.eml
```

Output is written as `<input-basename>.xml` in the same directory as the `.eml` file.

## Setup

None — `uv run` creates `.venv/` and installs dependencies on first use. To add a dependency, use `uv add <package>` (which updates both `pyproject.toml` and `uv.lock`) rather than editing `pyproject.toml` by hand.

## Architecture

`src/main.py` has three functions called in sequence by `main()`:

1. **`parse_email_file(path)`** — opens the `.eml`, finds the `text/html` part, and extracts form fields via regex patterns keyed on `<b><strong>Field Name</strong>` markers. Returns a `form_data` dict.

2. **`generate_datacite_xml(form_data, output_path)`** — builds a DataCite Kernel-4 XML tree with `lxml.etree`. The DOI identifier is always the placeholder `10.XXXX/XXXXX`. Creator name type (`Personal` vs `Organizational`) is inferred by presence of a comma. Calls `lookup_ror()` for organizational creators and the publisher.

3. **`lookup_ror(name)`** — checks the hard-coded `ROR_MAPPINGS` dict first, then falls back to the public ROR API (`https://api.ror.org/organizations`). Failures are non-fatal warnings.

Between parsing and XML generation, `process_email()` offers to edit the fields: `edit_form_data()` writes every key in `FIELD_PATTERNS` to a temp file as `key: value` lines, opens it in `$EDITOR`, and reads it back (blank values are dropped). Edits happen on the raw form values, so creator/ORCiD parsing and ROR lookup still run on the corrected text.

`clean_urldefense(url)` is a helper that strips URL-defense wrappers that university email systems inject around links.

## Key constraints

- The project is uv-managed and non-packaged (`[tool.uv] package = false`), so there is no build backend and `src/main.py` is run as a script, not imported.
- `uv.lock` and `.python-version` are tracked and should be committed alongside dependency changes.
- The regex patterns in `parse_email_file` are tightly coupled to the HTML structure of the DOI request form; changes to the form template require updating those patterns.
