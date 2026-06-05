"""
PDF Diagnostic Part 2 - Check data pages
"""
import sys, pdfplumber, re

pdf_path = sys.argv[1] if len(sys.argv) > 1 else input("PDF path: ").strip().strip('"')

with pdfplumber.open(pdf_path) as pdf:
    print(f"Total pages: {len(pdf.pages)}\n")
    # Check pages 2-5 for actual data rows
    for page_num in [2, 3, 4, 5]:
        if page_num >= len(pdf.pages):
            break
        page = pdf.pages[page_num]
        tables = page.extract_tables() or []
        print(f"\n=== PAGE {page_num+1}: {len(tables)} table(s) ===")
        for t_idx, table in enumerate(tables):
            print(f"  Table {t_idx+1}: {len(table)} rows")
            for row in table[:15]:
                # Print only non-empty cells
                cells = [str(c or '').strip()[:40] for c in row]
                non_empty = [c for c in cells if c]
                if non_empty:
                    print(f"    {cells[:8]}")  # first 8 cols
        
        # Also check words for x-position column layout
        words = page.extract_words() or []
        if words:
            print(f"\n  First 20 words (with x-pos):")
            for w in words[:20]:
                print(f"    x={w['x0']:6.1f}  top={w['top']:5.1f}  text={repr(w['text'][:60])}")
