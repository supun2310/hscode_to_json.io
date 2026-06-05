"""
PDF Diagnostic - Run this to see what pdfplumber extracts from your PDF.
Usage: py debug_pdf.py "your_file.pdf"
"""
import sys, pdfplumber

pdf_path = sys.argv[1] if len(sys.argv) > 1 else input("Enter PDF path: ").strip().strip('"')

with pdfplumber.open(pdf_path) as pdf:
    print(f"\n=== PDF has {len(pdf.pages)} pages ===\n")

    for page_num, page in enumerate(pdf.pages[:3], 1):  # first 3 pages
        print(f"\n{'='*60}")
        print(f"PAGE {page_num}")
        print(f"{'='*60}")

        # --- Raw text ---
        text = page.extract_text() or ""
        print("\n--- RAW TEXT (first 60 lines) ---")
        for line in text.splitlines()[:60]:
            print(repr(line))

        # --- Tables ---
        tables = page.extract_tables() or []
        print(f"\n--- TABLES FOUND: {len(tables)} ---")
        for t_idx, table in enumerate(tables):
            print(f"\n  Table {t_idx+1} ({len(table)} rows):")
            for r_idx, row in enumerate(table[:10]):  # first 10 rows
                print(f"    Row {r_idx}: {row}")

        # --- Words (first 40) ---
        words = page.extract_words() or []
        print(f"\n--- WORDS (first 40, with x-position) ---")
        for w in words[:40]:
            print(f"    x={w['x0']:6.1f}  text={repr(w['text'])}")

print("\n=== DONE ===")
