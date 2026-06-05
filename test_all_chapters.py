"""Regression test - verify fix doesn't break previously working chapters."""
import sys, os, glob
sys.stdout.reconfigure(encoding='utf-8')
from extractor import extract

pdfs = sorted(glob.glob(r'E:\bulk\*.pdf'))
print(f"Found {len(pdfs)} PDFs in E:\\bulk\\")
print()
ok_count = 0
err_count = 0
for p in pdfs:
    fname = os.path.basename(p)
    try:
        r = extract(p)
        items = len(r['items'])
        chap  = r['chapter']
        taxed = sum(1 for i in r['items'] if i.get('taxation_details'))
        status = 'OK ' if items > 0 else 'EMPTY'
        print(f"  [{status}] {fname} -> chapter={chap}, items={items}, with_tax={taxed}")
        if items > 0:
            ok_count += 1
        else:
            err_count += 1
    except Exception as e:
        print(f"  [ERR] {fname} -> {e}")
        err_count += 1

print()
print(f"Total: {ok_count} success, {err_count} failed/empty out of {len(pdfs)}")
