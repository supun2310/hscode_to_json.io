"""Debug Chapter 20 PDF to understand why no HS codes are extracted."""
import sys, pdfplumber, re
sys.stdout.reconfigure(encoding='utf-8')

pdf_path = r'E:\bulk\Tariff 2022 Section IV Final_Chap_20.pdf'

with pdfplumber.open(pdf_path) as pdf:
    print(f'Total pages: {len(pdf.pages)}')

    for p_idx, page in enumerate(pdf.pages[:6]):
        tables = page.extract_tables() or []
        print(f'\n{"="*60}')
        print(f'PAGE {p_idx+1}: {len(tables)} table(s)')
        for t_idx, table in enumerate(tables):
            if not table:
                continue
            ncols = len(table[0]) if table else 0
            print(f'  Table {t_idx+1}: {len(table)} rows x {ncols} cols')
            for r_idx, row in enumerate(table[:6]):
                cells = [str(c or '').replace('\n', ' ')[:20] for c in (row or [])]
                print(f'    Row {r_idx}: {cells}')

        # Also show raw text
        text = page.extract_text() or ''
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        print(f'  Text lines (first 15):')
        for ln in lines[:15]:
            print(f'    {repr(ln)}')
