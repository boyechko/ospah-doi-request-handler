# DOI Request Handler (Email → DataCite XML)

Small command-line utility that parses `.eml` messages from a DOI request form (HTML body) and produces a DataCite Kernel-4 metadata XML file suitable for import into DataCite Fabrica.

## Requirements

- Python 3.8+
- Dependencies: `lxml`, `requests` (see `requirements.txt`)

## Quick start

Create a virtualenv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the converter:

```bash
python src/main.py path/to/request.eml
```

This writes `path/to/request.xml` (same directory as the input `.eml`).

## What gets extracted

The script uses simple regex patterns against the email’s HTML body to extract:

- Requester name and email
- URL
- Creator(s)
- Title
- Publisher
- Publication year
- Resource type
- Description/abstract

It prints a readable “Extracted data” table to the terminal and then generates DataCite XML.

## DataCite output details

- The `<identifier>` is a placeholder (`10.XXXX/XXXXX`). DataCite assigns the real DOI when you register it.
- Creator parsing:
   - Multiple creators are separated by semicolons (`;`).
   - Names containing a comma are treated as `Personal` (e.g., `Last, First`).
   - Names without a comma are treated as `Organizational`.
- The `<resourceType>` is currently emitted with `resourceTypeGeneral="Dataset"`.

## ROR organization identifiers

For organizational creators and the publisher, the script attempts to add a ROR ID:

1. Checks a small local mapping (`ROR_MAPPINGS`) in `src/main.py`
2. Falls back to the public ROR API (`https://api.ror.org/organizations`)

If the lookup fails (offline, timeout, no matches), it continues without a ROR ID.

## Repository layout

- `src/main.py` — CLI entrypoint and conversion logic
- `data/` — sample `.eml` / `.xml` files
- `output/` — spare output folder (not currently used by the script)

## License

See `LICENSE`.
