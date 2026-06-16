import email
import re
from pathlib import Path
from lxml import etree
from html import unescape
import requests


# Common organization ROR mappings
ROR_MAPPINGS = {
    "Institute for Health Metrics and Evaluation": "https://ror.org/02684h094",
    "University of Washington": "https://ror.org/00cvxb145",
}


def lookup_ror(organization_name):
    """Look up ROR identifier for an organization."""
    # Check local mappings first
    if organization_name in ROR_MAPPINGS:
        return ROR_MAPPINGS[organization_name]

    # Try ROR API lookup
    try:
        response = requests.get(
            "https://api.ror.org/organizations",
            params={"query": organization_name},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("items") and len(data["items"]) > 0:
                # Return the first match
                return data["items"][0]["id"]
    except Exception as e:
        print(f"  Warning: Could not lookup ROR for '{organization_name}': {e}")

    return None


def clean_urldefense(url):
    """Strip URL defense wrapper from university email system."""
    if 'urldefense.com' in url:
        # Extract the actual URL between __ and __;
        match = re.search(r'__(.+?)__;', url)
        if match:
            return match.group(1)
    return url


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

    # Extract fields using regex patterns
    patterns = {
        'name': r'<b><strong>Your name</strong>:\s*</b><br>(.*?)<br>',
        'email': r'<b><strong>Your email address</strong>:\s*</b><br>(.*?)<br>',
        'url': r'<b><strong>URL</strong>.*?:\s*</b><br>\s*<a href="(.*?)"',
        'creators': r'<b><strong>Creator\(s\)</strong>.*?:\s*</b><br>(.*?)<br>',
        'title': r'<b><strong>Title</strong>.*?:\s*</b><br>(.*?)<br>',
        'publisher': r'<b><strong>Publisher</strong>.*?:\s*</b><br>(.*?)<br>',
        'publication_year': r'<b><strong>Publication Year</strong>.*?:\s*</b><br>\s*(\d{4})<br>',
        'resource_type': r'<b><strong>Resource Type</strong>.*?:\s*</b><br>(.*?)<br>',
        'description': r'<b><strong>Description</strong>.*?:\s*</b><br>(.*?)<br><br>',
    }

    for key, pattern in patterns.items():
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

    for creator_name in creator_list:
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
    resource_type = etree.SubElement(root, "resourceType", resourceTypeGeneral="Dataset")

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


def main():
    """Main function to process email and generate DataCite XML."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python main.py <email_file.eml>")
        print("\nExample:")
        print("  python main.py data/email.eml")
        print("\nOutput will be saved as <email_file>.xml")
        sys.exit(1)

    email_path = sys.argv[1]

    # Generate output path by replacing .eml extension with .xml
    output_path = Path(email_path).with_suffix('.xml')

    form_data = parse_email_file(email_path)

    print("\nExtracted data:")
    for key, value in form_data.items():
        display_value = f"{value[:120]}..." if len(str(value)) > 120 else str(value)
        # Use ANSI bold for keys and add visual separator
        print(f"  \033[1m{key:20}\033[0m │ {display_value}")

    # Generate XML
    print(f"\nGenerating DataCite XML...")
    generate_datacite_xml(form_data, output_path)


if __name__ == "__main__":
    main()
