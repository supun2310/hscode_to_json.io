"""Verify accuracy fixes for specific HS codes"""
import sys, json
sys.path.insert(0, r"C:\Users\Lenovo\Downloads\New folder (3)")
from extractor import extract

pdf = sys.argv[1] if len(sys.argv) > 1 else input("PDF: ").strip().strip('"')
result = extract(pdf)
items = {i['hs_code']: i for i in result['items']}

# Test cases that were wrong before
tests = [
    "8407.31",      # was level 2, parent of .10/.20/.90
    "8407.31.10",   # was level 2 (missing "Of a cylinder..." parent)
    "8407.31.90",   # same issue
    "8408.20",      # level 1
    "8408.20.10",   # was level 1 (missing "Engines of a kind..." parent)
    "8415.90",      # level 1, "Parts"
    "8415.90.10",   # should show Parts > Outdoor units
    "8415.90.11",   # should show Parts > Outdoor units > Used
]

for code in tests:
    item = items.get(code)
    if item:
        print(f"\n{'='*60}")
        print(f"HS Code : {item['hs_code']}")
        print(f"Level   : {item['hierarchical_level']}")
        print(f"Self    : {item['self_description']}")
        print(f"Path    : {item['hierarchy_path']}")
    else:
        print(f"\n[NOT FOUND] {code}")

print(f"\n\nTotal items: {len(result['items'])}")
