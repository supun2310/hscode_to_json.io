"""Quick test - run extractor on the actual PDF and show first 5 items"""
import sys, json
sys.path.insert(0, r"C:\Users\Lenovo\Downloads\New folder (3)")
from extractor import extract

pdf = sys.argv[1] if len(sys.argv) > 1 else input("PDF path: ").strip().strip('"')
result = extract(pdf)

print(f"\nChapter   : {result['chapter']}")
print(f"Desc      : {result['chapter_description']}")
print(f"Items     : {len(result['items'])}")
print(f"Exceptions: {len(result['chapter_exceptions'])}")
print("\n--- First 5 items ---")
for item in result['items'][:5]:
    print(json.dumps(item, indent=2))
