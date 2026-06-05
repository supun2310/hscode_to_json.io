"""
Quick test: show what tax columns are detected from a PDF and
print the first 3 items with their taxation_details.
Usage: python test_tax.py path/to/chapter.pdf
"""
import sys, json, pdfplumber
sys.stdout.reconfigure(encoding='utf-8')

from extractor import extract, detect_tax_col_map

pdf_path = sys.argv[1] if len(sys.argv) > 1 else None
if not pdf_path:
    print("Usage: python test_tax.py path/to/chapter.pdf")
    sys.exit(1)

print(f"\n=== Tax Column Detection ===")
with pdfplumber.open(pdf_path) as pdf:
    for p_idx, page in enumerate(pdf.pages[:3]):
        tables = page.extract_tables() or []
        for t_idx, table in enumerate(tables):
            if not table:
                continue
            col_map = detect_tax_col_map(table)
            if col_map:
                print(f"\nPage {p_idx+1}, Table {t_idx+1}: col_map = {col_map}")
                print(f"  Table has {len(table[0]) if table else 0} columns")
                print(f"  First 3 header rows:")
                for row in table[:3]:
                    cells = [str(c or '').replace('\n',' ')[:20] for c in row]
                    print(f"    {cells}")
                break

print(f"\n=== Extraction Result ===")
result = extract(pdf_path)
print(f"Chapter : {result['chapter']}")
print(f"Items   : {len(result['items'])}")
print()

items_with_tax    = [i for i in result['items'] if i.get('taxation_details')]
items_without_tax = [i for i in result['items'] if not i.get('taxation_details')]
print(f"Items WITH taxation_details   : {len(items_with_tax)}")
print(f"Items WITHOUT taxation_details: {len(items_without_tax)}")

print(f"\n=== First 3 items with tax data ===")
for item in items_with_tax[:3]:
    print(json.dumps(item, indent=2, ensure_ascii=False))
    print()
