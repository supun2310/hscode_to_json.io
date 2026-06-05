"""Debug column layout of Chapter 20 PDF."""
import pdfplumber, sys
sys.stdout.reconfigure(encoding='utf-8')

pdf_path = r'E:\bulk\Tariff 2022 Section IV Final_Chap_20.pdf'
with pdfplumber.open(pdf_path) as pdf:
    # Check page 2 (index 1 = page 2)
    for page_idx in [1, 2]:
        page = pdf.pages[page_idx]
        tables = page.extract_tables() or []
        print(f'\n=== PAGE {page_idx+1}: {len(tables)} tables ===')
        for ti, t in enumerate(tables):
            ncols = len(t[0]) if t else 0
            print(f'Table {ti+1}: {len(t)} rows x {ncols} cols')
            print('--- Header rows (0-4) ---')
            for ri, row in enumerate(t[:5]):
                cells = [str(c or '').replace('\n',' ')[:20] for c in row]
                print(f'  Row {ri}: {cells}')
            print('--- Data rows (5-12) ---')
            for ri, row in enumerate(t[5:13], 5):
                cells = [str(c or '').replace('\n',' ')[:25] for c in row]
                print(f'  Row {ri}: {cells}')
