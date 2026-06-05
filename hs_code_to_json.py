"""
HS Code PDF to JSON Extractor
==============================
Extracts HS codes and descriptions from a PDF file and saves them as JSON.

Supports:
  - Text-based PDFs (via pdfplumber / PyMuPDF)
  - Table-structured PDFs
  - Multi-line descriptions
  - Fallback regex parsing

Requirements:
  pip install pdfplumber pymupdf
"""

import re
import json
import sys
import os
import argparse
import logging
from pathlib import Path
from typing import Optional

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── HS-code pattern (2–10 digits, with optional dots/spaces) ─────────────────
HS_PATTERN = re.compile(
    r"""
    ^\s*                          # optional leading whitespace
    (?P<code>
        \d{2}                     # 2-digit chapter
        (?:[.\s]?\d{2}            # 4-digit heading (dot optional)
        (?:[.\s]?\d{2}            # 6-digit subheading
        (?:[.\s]?\d{2}            # 8-digit
        (?:[.\s]?\d{2})?          # 10-digit
        )?)?)?
    )
    \s*[|:\t]?\s*                 # optional separator
    (?P<description>.+?)          # description
    \s*$
    """,
    re.VERBOSE,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def clean_code(raw: str) -> str:
    """Normalise an HS code to digits-only (e.g. '01.02.10' → '010210')."""
    return re.sub(r"[.\s]", "", raw).strip()


def clean_text(text: str) -> str:
    """Remove excess whitespace / control characters from description."""
    return re.sub(r"\s+", " ", text).strip()


def extract_with_pdfplumber(pdf_path: str) -> list[dict]:
    """
    Primary extraction strategy using pdfplumber.
    Tries table extraction first, then falls back to raw text.
    """
    try:
        import pdfplumber
    except ImportError:
        log.warning("pdfplumber not installed. Run: pip install pdfplumber")
        return []

    results: list[dict] = []
    log.info("Trying pdfplumber …")

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            # ── 1. Try table extraction ──────────────────────────────────────
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        row = [cell or "" for cell in row]
                        # Detect which column looks like an HS code
                        code_col, desc_col = _find_code_column(row)
                        if code_col is not None and desc_col is not None:
                            code = clean_code(row[code_col])
                            desc = clean_text(" ".join(
                                str(row[c]) for c in range(len(row))
                                if c != code_col and row[c]
                            )) if desc_col == -1 else clean_text(row[desc_col])
                            if code:
                                results.append({
                                    "hs_code": code,
                                    "description": desc,
                                    "page": page_num,
                                })
                log.info(f"  Page {page_num}: extracted {len([r for r in results if r['page']==page_num])} rows from tables")
                continue  # skip raw-text pass if tables found

            # ── 2. Raw-text fallback ─────────────────────────────────────────
            text = page.extract_text() or ""
            page_results = parse_text_lines(text, page_num)
            results.extend(page_results)
            log.info(f"  Page {page_num}: extracted {len(page_results)} rows from raw text")

    return results


def extract_with_pymupdf(pdf_path: str) -> list[dict]:
    """
    Fallback extraction strategy using PyMuPDF (fitz).
    Works well with digitally-generated PDFs.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        log.warning("PyMuPDF not installed. Run: pip install pymupdf")
        return []

    results: list[dict] = []
    log.info("Trying PyMuPDF …")

    doc = fitz.open(pdf_path)
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        page_results = parse_text_lines(text, page_num)
        results.extend(page_results)
        log.info(f"  Page {page_num}: extracted {len(page_results)} rows")

    doc.close()
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  Text parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_text_lines(text: str, page_num: int = 0) -> list[dict]:
    """
    Parse raw text line-by-line using the HS_PATTERN regex.
    Merges continuation lines (lines that don't start with an HS code)
    into the previous entry's description.
    """
    results: list[dict] = []
    current: Optional[dict] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m = HS_PATTERN.match(line)
        if m:
            code = clean_code(m.group("code"))
            # Skip lines where the "code" is implausibly short (< 2 digits)
            if len(code) < 2:
                if current:
                    current["description"] += " " + clean_text(line)
                continue

            if current:
                results.append(current)

            current = {
                "hs_code": code,
                "description": clean_text(m.group("description")),
                "page": page_num,
            }
        else:
            # Continuation line — append to previous entry
            if current:
                current["description"] += " " + clean_text(line)

    if current:
        results.append(current)

    return results


def _find_code_column(row: list) -> tuple[Optional[int], Optional[int]]:
    """
    Given a table row, identify which column contains an HS code and
    which contains the description.  Returns (code_col, desc_col).
    desc_col == -1 means 'everything else'.
    """
    code_col = None
    desc_col = None
    max_text_len = 0

    for i, cell in enumerate(row):
        cell_str = str(cell).strip()
        cleaned = clean_code(cell_str)
        if re.fullmatch(r"\d{2,10}", cleaned) and len(cleaned) % 2 == 0:
            code_col = i
        elif len(cell_str) > max_text_len:
            max_text_len = len(cell_str)
            desc_col = i

    return code_col, desc_col


# ─────────────────────────────────────────────────────────────────────────────
#  De-duplication & post-processing
# ─────────────────────────────────────────────────────────────────────────────

def deduplicate(records: list[dict]) -> list[dict]:
    """Remove duplicate HS codes, keeping the entry with the longest description."""
    seen: dict[str, dict] = {}
    for rec in records:
        code = rec["hs_code"]
        if code not in seen or len(rec["description"]) > len(seen[code]["description"]):
            seen[code] = rec
    return list(seen.values())


def postprocess(records: list[dict], *, keep_page: bool = False) -> list[dict]:
    """Final clean-up: strip page numbers, empty descriptions, etc."""
    cleaned = []
    for rec in records:
        desc = rec["description"].strip(" -|:,;")
        if not desc:
            desc = "(no description)"
        entry = {"hs_code": rec["hs_code"], "description": desc}
        if keep_page:
            entry["page"] = rec.get("page", 0)
        cleaned.append(entry)
    return cleaned


# ─────────────────────────────────────────────────────────────────────────────
#  Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def extract_hs_codes(pdf_path: str, keep_page: bool = False) -> list[dict]:
    """
    Full extraction pipeline:
      1. Try pdfplumber (best for tables)
      2. Fall back to PyMuPDF (best for continuous text)
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path!r}")

    records = extract_with_pdfplumber(pdf_path)

    if not records:
        log.info("pdfplumber returned no results; trying PyMuPDF …")
        records = extract_with_pymupdf(pdf_path)

    if not records:
        log.error("Could not extract any HS codes. Is the PDF text-based?")
        return []

    records = deduplicate(records)
    records = postprocess(records, keep_page=keep_page)
    records.sort(key=lambda r: r["hs_code"])
    return records


def save_json(records: list[dict], output_path: str, indent: int = 2) -> None:
    """Write records to a JSON file."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=indent)
    log.info(f"Saved {len(records)} records → {output_path!r}")


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract HS codes from a PDF and save as JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python hs_code_to_json.py tariff.pdf
  python hs_code_to_json.py tariff.pdf -o output.json
  python hs_code_to_json.py tariff.pdf --keep-page --indent 4
        """,
    )
    parser.add_argument("pdf", help="Path to the input PDF file")
    parser.add_argument(
        "-o", "--output",
        help="Output JSON file path (default: <pdf_name>.json)",
    )
    parser.add_argument(
        "--keep-page",
        action="store_true",
        help="Include page number in each record",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation level (default: 2)",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Also print the JSON to stdout",
    )
    return parser


def main() -> None:
    parser = build_cli()
    args = parser.parse_args()

    pdf_path = args.pdf
    output_path = args.output or str(Path(pdf_path).with_suffix(".json"))

    log.info(f"Input PDF : {pdf_path!r}")
    log.info(f"Output JSON: {output_path!r}")

    records = extract_hs_codes(pdf_path, keep_page=args.keep_page)

    if not records:
        log.error("No HS codes were extracted. Exiting.")
        sys.exit(1)

    save_json(records, output_path, indent=args.indent)

    if args.print:
        print(json.dumps(records, ensure_ascii=False, indent=args.indent))

    log.info("Done ✓")


if __name__ == "__main__":
    main()
