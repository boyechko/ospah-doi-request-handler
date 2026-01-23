# DOI Request Email to DataCite XML Converter

This script parses email messages from the DOI Request Form and generates DataCite metadata XML files that can be imported into DataCite's Fabrica.

## Setup

Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

```bash
python src/main.py <email_file.eml>
```

The output XML file will be saved in the `output/` directory with a filename based on the input file name.

## What it does

The script:
1. Parses the .eml email file
2. Extracts form data from the HTML body including:
   - Creator(s)
   - Title
   - Publisher
   - Publication Year
   - Resource Type
   - Description
   - URL
3. Generates a DataCite-compliant XML file following the kernel-4 schema

## Notes

- The DOI identifier in the generated XML is set to a placeholder (`10.XXXX/XXXXX`) and will be assigned by DataCite upon registration
- Multiple creators can be separated by semicolons in the form
- Personal names should be in "Last, First" format
- Organizational names are automatically detected (no comma)
