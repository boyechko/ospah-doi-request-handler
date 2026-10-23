import email
import os
import re
import shlex
import tempfile
import unicodedata
import subprocess
from datetime import datetime
from pathlib import Path
from lxml import etree
from html import unescape
import requests


# Common organization ROR mappings
ROR_MAPPINGS = {
    "Institute for Health Metrics and Evaluation": "https://ror.org/02684h094",
    "National Alzheimer's Coordinating Center": "https://ror.org/03qm4p447",
    "University of Washington": "https://ror.org/00cvxb145",
}


def normalize_org_name(name):
    """Normalize an organization name for comparison (quotes, dashes, spacing)."""
    name = unicodedata.normalize("NFKC", name)
    name = name.translate(str.maketrans("\u2018\u2019\u201c\u201d\u2013\u2014", "''\"\"--"))
    return " ".join(name.split()).casefold()


def lookup_ror(organization_name):
    """Look up ROR identifier for an organization."""
    # Check local mappings first
    if organization_name in ROR_MAPPINGS:
        return ROR_MAPPINGS[organization_name]

    # Try ROR API lookup: quote the query so it is matched as a phrase, then
    # accept only an organization whose name (or alias) matches exactly, since
    # even a phrase query returns related organizations (e.g. "University of
    # Washington" also matches "University of Washington Bothell").
    try:
        response = requests.get(
            "https://api.ror.org/v2/organizations",
            params={"query": f'"{organization_name}"'},
            timeout=5
        )
        if response.status_code == 200:
            target = normalize_org_name(organization_name)
            for item in response.json().get("items", []):
                if any(normalize_org_name(name["value"]) == target
                       for name in item.get("names", [])):
                    return item["id"]
    except Exception as e:
        print(f"  Warning: Could not lookup ROR for '{organization_name}': {e}")

    return None


ORCID_RE = re.compile(r'(?:https?://(?:www\.)?orcid\.org/)?(\d{4}-\d{4}-\d{4}-\d{3}[\dX])', re.IGNORECASE)


def parse_creator(creator_text):
    """Split one creator entry into (name, orcid).

    The form asks for "Last name, First name, ORCiD"; the ORCiD may be a bare
    identifier or an orcid.org URL. Returns the ORCiD as a bare identifier, or
    None if the entry doesn't include one.
    """
    orcid = None
    match = ORCID_RE.search(creator_text)
    if match:
        orcid = match.group(1).upper()
        creator_text = ORCID_RE.sub('', creator_text)
        # Drop the orcid.org URL remnant and the comma that introduced it
        creator_text = re.sub(r'https?://\S*', '', creator_text)
        creator_text = creator_text.strip().rstrip(',').strip()

    return creator_text, orcid


def clean_urldefense(url):
    """Strip URL defense wrapper from university email system."""
    if 'urldefense.com' in url:
        # Extract the actual URL between __ and __;
        match = re.search(r'__(.+?)__;', url)
        if match:
            return match.group(1)
    return url


# Form fields extracted from the request email's HTML body, keyed on the
# form_data key each one populates.
FIELD_PATTERNS = {
    'submitted': r'<b>Submitted:</b>\s*(.*?)<br>',
    'submission_id': r'<b>Submission ID:</b>\s*(.*?)<br>',
    'name': r'<b><strong>Your name</strong>:\s*</b><br>(.*?)<br>',
    'email': r'<b><strong>Your email address</strong>:\s*</b><br>(.*?)<br>',
    'title': r'<b><strong>Title</strong>.*?:\s*</b><br>(.*?)<br>',
    'resource_type': r'<b><strong>Resource Type</strong>.*?:\s*</b><br>(.*?)<br>',
    'url': r'<b><strong>URL</strong>.*?:\s*</b><br>\s*<a href="(.*?)"',
    'creators': r'<b><strong>Creator\(s\)</strong>.*?:\s*</b><br>(.*?)<br>',
    'publisher': r'<b><strong>Publisher</strong>.*?:\s*</b><br>(.*?)<br>',
    'publication_year': r'<b><strong>Publication Year</strong>.*?:\s*</b><br>\s*(\d{4})<br>',
    'description': r'<b><strong>Description</strong>.*?:\s*</b><br>(.*?)<br><br>',
}


def parse_email_file(email_path):
    """Parse an .eml file and extract form data."""
    with open(email_path, 'r', encoding='utf-8') as f:
        msg = email.message_from_file(f)

    # Get the HTML body
    html_body = None
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                break
    else:
        if msg.get_content_type() == 'text/html':
            html_body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

    if not html_body:
        raise ValueError("No HTML body found in email")

    # Parse form fields from HTML
    form_data = {}

    for key, pattern in FIELD_PATTERNS.items():
        match = re.search(pattern, html_body, re.DOTALL | re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            # Clean up HTML entities and tags
            value = unescape(value)
            value = re.sub(r'<[^>]+>', '', value)
            # Clean URL defense wrapper
            if key == 'url':
                value = clean_urldefense(value)
            form_data[key] = value

    return form_data


def generate_datacite_xml(form_data, output_path):
    """Generate DataCite XML from parsed form data."""

    # Create root element with namespaces
    NSMAP = {
        None: "http://datacite.org/schema/kernel-4",
        "xsi": "http://www.w3.org/2001/XMLSchema-instance"
    }

    root = etree.Element(
        "resource",
        nsmap=NSMAP,
        attrib={
            "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation":
            "http://datacite.org/schema/kernel-4 http://schema.datacite.org/meta/kernel-4/metadata.xsd"
        }
    )

    # Identifier (placeholder - will be assigned by DataCite)
    identifier = etree.SubElement(root, "identifier", identifierType="DOI")
    identifier.text = "10.XXXX/XXXXX"

    # Creators
    creators = etree.SubElement(root, "creators")
    creator_text = form_data.get('creators', '')

    # Split by semicolon for multiple creators
    creator_list = [c.strip() for c in creator_text.split(';') if c.strip()]

    for creator_entry in creator_list:
        creator_name, orcid = parse_creator(creator_entry)
        creator = etree.SubElement(creators, "creator")

        # Check if it's an organizational name (no comma) or personal name
        if ',' in creator_name:
            # Personal name: Last, First
            name_type = "Personal"
        else:
            # Organizational name
            name_type = "Organizational"

        creator_name_elem = etree.SubElement(creator, "creatorName", nameType=name_type)
        creator_name_elem.text = creator_name

        if name_type == "Personal":
            family, given = [part.strip() for part in creator_name.split(',', 1)]
            etree.SubElement(creator, "givenName").text = given
            etree.SubElement(creator, "familyName").text = family

            if orcid:
                name_identifier = etree.SubElement(creator, "nameIdentifier",
                                                   nameIdentifierScheme="ORCID",
                                                   schemeURI="https://orcid.org/")
                name_identifier.text = orcid
                print(f"  Added ORCiD for creator '{creator_name}': {orcid}")

        # Add ROR identifier for organizational creators
        if name_type == "Organizational":
            ror_id = lookup_ror(creator_name)
            if ror_id:
                name_identifier = etree.SubElement(creator, "nameIdentifier",
                                                   nameIdentifierScheme="ROR",
                                                   schemeURI="https://ror.org")
                name_identifier.text = ror_id
                print(f"  Added ROR for creator '{creator_name}': {ror_id}")

    # Titles
    titles = etree.SubElement(root, "titles")
    title = etree.SubElement(titles, "title")
    title.set("{http://www.w3.org/XML/1998/namespace}lang", "en")
    title.text = form_data.get('title', '')

    # Publisher
    publisher_name = form_data.get('publisher', '')
    publisher = etree.SubElement(root, "publisher")
    publisher.text = publisher_name

    # Add ROR identifier if available
    if publisher_name:
        ror_id = lookup_ror(publisher_name)
        if ror_id:
            publisher.set("publisherIdentifier", ror_id)
            publisher.set("publisherIdentifierScheme", "ROR")
            publisher.set("schemeURI", "https://ror.org")
            print(f"  Added ROR for publisher: {ror_id}")

    # Publication Year
    pub_year = etree.SubElement(root, "publicationYear")
    pub_year.text = form_data.get('publication_year', '')

    # Resource Type
    resource_type = etree.SubElement(root, "resourceType",
                                     resourceTypeGeneral=form_data.get('resource_type', 'Dataset'))

    # Optional elements
    etree.SubElement(root, "sizes")
    etree.SubElement(root, "formats")
    etree.SubElement(root, "version")

    # Descriptions
    if form_data.get('description'):
        descriptions = etree.SubElement(root, "descriptions")
        description = etree.SubElement(descriptions, "description", descriptionType="Abstract")
        description.set("{http://www.w3.org/XML/1998/namespace}lang", "en")
        description.text = form_data.get('description', '')

    # Write to file
    tree = etree.ElementTree(root)
    tree.write(
        output_path,
        pretty_print=True,
        xml_declaration=True,
        encoding='UTF-8'
    )

    print(f"\nGenerated DataCite XML:\n  {output_path}")


def format_submission_date(submitted):
    """Convert a 'Jun 15, 2026 08:22 AM' submitted value to M/D/YYYY."""
    if not submitted:
        return ""
    for fmt in ("%b %d, %Y %I:%M %p", "%b %d, %Y"):
        try:
            dt = datetime.strptime(submitted.strip(), fmt)
            return f"{dt.month}/{dt.day}/{dt.year}"
        except ValueError:
            continue
    # Unrecognized format: fall back to the raw value
    return submitted.strip()


# Tracking-spreadsheet columns, in order. Each entry maps a column header to the
# form_data key it comes from; None means the column isn't available from the
# email (Owner, Status, DOI, etc. are filled in by hand later).
TRACKING_COLUMNS = [
    ("Submission ID", "submission_id"),
    ("Requester", "name"),
    ("Requester Email Address", "email"),
    ("Title", "title"),
    ("Resource Type", "resource_type"),
    ("Owner", None),
    ("Status", None),
    ("Date of Submission", "submitted"),
    ("Date of DOI Creation", None),
    ("Landing Page URL", "url"),
    ("DOI", None),
    ("Notes", None),
    ("Correspondence/Any relevenat reference", None),
]


def copy_tracking_row(form_data):
    """Copy a tab-separated tracking row to the clipboard for pasting into the
    DOI Requests Tracking spreadsheet."""
    values = []
    for header, key in TRACKING_COLUMNS:
        if key is None:
            values.append("")
        elif key == "submitted":
            values.append(format_submission_date(form_data.get("submitted", "")))
        else:
            values.append(form_data.get(key, ""))

    row = "\t".join(values)

    try:
        subprocess.run(["pbcopy"], input=row, text=True, check=True)
        print("\nCopied tracking row to clipboard (paste into the spreadsheet).")
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"\nWarning: Could not copy to clipboard: {e}")
        print(f"Tracking row:\n{row}")


def print_form_data(form_data):
    """Print the form fields, truncating long values."""
    print("\nExtracted data:")
    for key, value in form_data.items():
        display_value = f"{value[:120]}..." if len(str(value)) > 120 else str(value)
        # Use ANSI bold for keys and add visual separator
        print(f"  \033[1m{key:20}\033[0m │ {display_value}")


def edit_form_data(form_data):
    """Open the form fields in $EDITOR as 'key: value' lines and return the
    edited values. Every known field is listed, so ones the parser missed can
    be filled in; fields left blank are dropped."""
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("# One field per line as 'key: value'. Blank values are dropped; lines starting with # are ignored.\n")
        for key in FIELD_PATTERNS:
            value = form_data.get(key, '').replace('\n', ' ')
            f.write(f"{key}: {value}\n")
        edit_path = f.name

    try:
        subprocess.run(shlex.split(os.environ.get('EDITOR', 'vi')) + [edit_path], check=True)
        lines = Path(edit_path).read_text(encoding='utf-8').splitlines()
    finally:
        os.unlink(edit_path)

    edited = {}
    for line in lines:
        if line.startswith('#') or ':' not in line:
            continue
        key, value = line.split(':', 1)
        if value.strip():
            edited[key.strip()] = value.strip()
    return edited


def process_email(email_path):
    """Process a single .eml file and generate its DataCite XML."""
    # Generate output path by replacing .eml extension with .xml
    output_path = Path(email_path).with_suffix('.xml')

    form_data = parse_email_file(email_path)
    print_form_data(form_data)

    # Offer to correct the requester's answers until they look right
    while True:
        try:
            answer = input("\nEdit fields before generating XML? [y/N] ")
        except EOFError:
            break
        if not answer.strip().lower().startswith('y'):
            break
        form_data = edit_form_data(form_data)
        print_form_data(form_data)

    # Generate XML
    print(f"\nGenerating DataCite XML...")
    generate_datacite_xml(form_data, output_path)

    # Copy the tracking-spreadsheet row to the clipboard
    copy_tracking_row(form_data)


def main():
    """Main function to process one or more emails and generate DataCite XML."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python main.py <email_file.eml> [more.eml ...]")
        print("\nExample:")
        print("  python main.py request.eml")
        print("  python main.py *.eml")
        print("\nOutput will be saved as <email_file>.xml")
        sys.exit(1)

    # Process in alphanumeric order regardless of shell/glob ordering.
    email_paths = sorted(sys.argv[1:])
    total = len(email_paths)

    for index, email_path in enumerate(email_paths, start=1):
        print(f"\n\033[1m═══ [{index}/{total}] {email_path} \033[0m")
        try:
            process_email(email_path)
        except Exception as e:
            print(f"\n\033[31mError processing '{email_path}': {e}\033[0m")

        # Pause after each file (except the last) so the tracking row can be
        # pasted before the next file overwrites the clipboard.
        if index < total:
            try:
                input("\nPress Enter for the next file (Ctrl-C to stop)... ")
            except (EOFError, KeyboardInterrupt):
                print("\nStopped.")
                break


if __name__ == "__main__":
    main()
