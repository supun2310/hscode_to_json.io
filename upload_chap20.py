"""
upload_chap20.py
================
Extracts Chapter 20 from the fixed PDF and upserts only those HS codes
into MongoDB.  All other chapters in the DB are left completely untouched.

This script is safe to run multiple times (idempotent upsert on _id = hs_code).

Usage:
  python upload_chap20.py
  python upload_chap20.py "E:\\bulk\\Tariff 2022 Section IV Final_Chap_20.pdf"
"""

import sys, os, traceback
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime, timezone
from pymongo import MongoClient, UpdateOne
from pymongo.server_api import ServerApi
from extractor import extract

# ── Config ────────────────────────────────────────────────────────────────────
MONGO_URI = "mongodb+srv://udanaravindurv_db_user:RqWgEd8CMHxb5Ttp@cluster0.huccgsz.mongodb.net/?appName=Cluster0"
DB_NAME   = "wizard"
COL_NAME  = "hscodes"

DEFAULT_PDF = r"E:\bulk\Tariff 2022 Section IV Final_Chap_20.pdf"

# ── Helpers ───────────────────────────────────────────────────────────────────

def connect():
    print("  Connecting to MongoDB ...", end=" ", flush=True)
    client = MongoClient(MONGO_URI, server_api=ServerApi('1'), serverSelectionTimeoutMS=15_000)
    client.admin.command('ping')
    col = client[DB_NAME][COL_NAME]
    # Ensure indexes (idempotent)
    col.create_index("chapter")
    col.create_index("heading")
    col.create_index([("hs_code", 1)], unique=True)
    print(f"OK  →  {DB_NAME}.{COL_NAME}")
    return col


def build_doc(item: dict, chapter_info: dict, source_file: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "_id"                      : item["hs_code"],
        "hs_code"                  : item["hs_code"],
        "chapter"                  : chapter_info.get("chapter", ""),
        "chapter_description"      : chapter_info.get("chapter_description", ""),
        "chapter_exceptions"       : chapter_info.get("chapter_exceptions", []),
        "heading"                  : item.get("heading", ""),
        "heading_description"      : item.get("heading_description", ""),
        "hierarchical_level"       : item.get("hierarchical_level", 0),
        "hierarchy_path"           : item.get("hierarchy_path", ""),
        "self_description"         : item.get("self_description", ""),
        "full_context_description" : item.get("full_context_description", ""),
        "unit"                     : item.get("unit", ""),
        "taxation_details"         : item.get("taxation_details", None),
        "source_file"              : source_file,
        "imported_at"              : now,
    }


def upsert_docs(col, docs: list) -> tuple:
    if not docs:
        return 0, 0, []
    ops = [UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True) for d in docs]
    errors = []
    inserted = modified = 0
    try:
        r = col.bulk_write(ops, ordered=False)
        inserted = r.upserted_count
        modified = r.modified_count
    except Exception as e:
        det = getattr(e, 'details', {})
        inserted = det.get('nUpserted', 0)
        modified = det.get('nModified', 0)
        for we in det.get('writeErrors', []):
            errors.append(we.get('errmsg', str(we)))
    return inserted, modified, errors


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PDF
    pdf_path = os.path.abspath(pdf_path)

    if not os.path.isfile(pdf_path):
        print(f"\n[ERROR] PDF not found: {pdf_path}")
        sys.exit(1)

    fname = os.path.basename(pdf_path)

    print("\n" + "="*60)
    print("  Chapter 20 – Targeted Upload")
    print(f"  PDF    : {pdf_path}")
    print("="*60 + "\n")

    # ── Extract ───────────────────────────────────────────────────────────────
    print("  Extracting HS codes from PDF ...")
    try:
        result = extract(pdf_path)
    except Exception as e:
        print(f"  [FATAL] Extraction failed: {e}")
        traceback.print_exc()
        sys.exit(1)

    items   = result.get("items", [])
    chap_no = result.get("chapter", "??")

    print(f"  Chapter : {chap_no}")
    print(f"  Items   : {len(items)} HS codes extracted")

    if not items:
        print("  [ERROR] No HS code items found — aborting upload.")
        sys.exit(1)

    taxed = sum(1 for i in items if i.get("taxation_details"))
    print(f"  Tax data: {taxed}/{len(items)} items have taxation_details")

    chapter_info = {
        "chapter"            : result.get("chapter", ""),
        "chapter_description": result.get("chapter_description", ""),
        "chapter_exceptions" : result.get("chapter_exceptions", []),
    }

    # ── Build documents ───────────────────────────────────────────────────────
    docs = []
    for item in items:
        try:
            docs.append(build_doc(item, chapter_info, fname))
        except Exception as e:
            print(f"  [WARN] Build error for hs_code={item.get('hs_code','?')}: {e}")

    print(f"  Built   : {len(docs)} documents ready for upsert")

    # ── Connect & Upload ──────────────────────────────────────────────────────
    try:
        col = connect()
    except Exception as e:
        print(f"  [FATAL] MongoDB connection failed: {e}")
        sys.exit(1)

    print(f"  Uploading {len(docs)} docs to MongoDB (upsert) ...", end=" ", flush=True)
    ins, mod, errs = upsert_docs(col, docs)
    print("Done")

    print()
    print("="*60)
    print("  UPLOAD RESULT")
    print("="*60)
    print(f"  Inserted (new)  : {ins}")
    print(f"  Updated (exist) : {mod}")
    print(f"  Errors          : {len(errs)}")
    if errs:
        print("  Error details:")
        for e in errs:
            print(f"    - {e}")
    else:
        print("  ✅ All Chapter 20 HS codes upserted successfully!")
        print("  ✅ All other chapters in the DB remain untouched.")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
