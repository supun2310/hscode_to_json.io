"""
bulk_import.py
==============
Reads every PDF in a given folder, extracts all HS codes using extractor.py,
and stores each HS code as one individual document in MongoDB.

Database  : hscodes
Collection: hscode_items

Document shape (one per HS code):
{
  "_id"                   : "<hs_code>",          # used as unique key
  "hs_code"               : "8407.31.10",
  "chapter"               : "84",
  "chapter_description"   : "...",
  "chapter_exceptions"    : [...],
  "heading"               : "84.07",
  "heading_description"   : "...",
  "hierarchical_level"    : 2,
  "hierarchy_path"        : "... > ... > ...",
  "self_description"      : "...",
  "full_context_description": "...",
  "unit"                  : "U",
  "taxation_details"      : {
      "general_duty": "Free",
      "vat"         : "18%",
      "pal"         : "Ex",
      "cess"        : null,
      "excise_spd"  : null,
      "sscl"        : "2.5%",
      "preferential_agreements": { "in": "Free", "pk": "Free", ... }
  },
  "source_file"           : "chapter_84.pdf",
  "imported_at"           : "<ISO timestamp>"
}

Usage:
  python bulk_import.py                       # uses ./pdfs  folder by default
  python bulk_import.py C:/path/to/pdf/folder
"""

import sys
import os
import glob
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

# ── stdout utf-8 ──────────────────────────────────────────────────────────────
sys.stdout.reconfigure(encoding='utf-8')

# ── MongoDB ───────────────────────────────────────────────────────────────────
from pymongo import MongoClient, UpdateOne
from pymongo.server_api import ServerApi

MONGO_URI  = "mongodb+srv://udanaravindurv_db_user:RqWgEd8CMHxb5Ttp@cluster0.huccgsz.mongodb.net/?appName=Cluster0"
DB_NAME    = "wizard"
COL_NAME   = "hscodes"

# ── Local extractor ────────────────────────────────────────────────────────────
from extractor import extract   # your existing extractor.py


# ═════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═════════════════════════════════════════════════════════════════════════════

def connect_mongo():
    """Connect to MongoDB and return the target collection."""
    print("  Connecting to MongoDB...", end=" ", flush=True)
    client = MongoClient(MONGO_URI, server_api=ServerApi('1'), serverSelectionTimeoutMS=15_000)
    client.admin.command('ping')
    col = client[DB_NAME][COL_NAME]
    print(f"OK  →  {DB_NAME}.{COL_NAME}")
    return col


def ensure_indexes(col):
    """Create useful indexes (idempotent)."""
    col.create_index("chapter")
    col.create_index("heading")
    col.create_index("hierarchical_level")
    col.create_index([("hs_code", 1)], unique=True)


def build_document(item: dict, chapter_info: dict, source_file: str) -> dict:
    """
    Combine an extractor item with chapter-level metadata into one MongoDB document.
    '_id' is set to the hs_code so re-running is idempotent (upsert).
    """
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "_id"                     : item["hs_code"],
        "hs_code"                 : item["hs_code"],
        "chapter"                 : chapter_info.get("chapter", ""),
        "chapter_description"     : chapter_info.get("chapter_description", ""),
        "chapter_exceptions"      : chapter_info.get("chapter_exceptions", []),
        "heading"                 : item.get("heading", ""),
        "heading_description"     : item.get("heading_description", ""),
        "hierarchical_level"      : item.get("hierarchical_level", 0),
        "hierarchy_path"          : item.get("hierarchy_path", ""),
        "self_description"        : item.get("self_description", ""),
        "full_context_description": item.get("full_context_description", ""),
        "unit"                    : item.get("unit", ""),
        "taxation_details"        : item.get("taxation_details", None),
        "source_file"             : source_file,
        "imported_at"             : now,
    }
    return doc


def upsert_items(col, docs: list) -> tuple:
    """
    Bulk-upsert a list of documents.
    Returns (inserted_count, modified_count, error_count, error_details).
    """
    if not docs:
        return 0, 0, 0, []

    ops = [
        UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True)
        for d in docs
    ]
    errors = []
    inserted = modified = 0
    try:
        result = col.bulk_write(ops, ordered=False)
        inserted = result.upserted_count
        modified = result.modified_count
    except Exception as e:
        # BulkWriteError carries partial results
        bwe = getattr(e, 'details', {})
        inserted = bwe.get('nUpserted', 0)
        modified = bwe.get('nModified', 0)
        write_errors = bwe.get('writeErrors', [])
        for we in write_errors:
            errors.append({
                "index": we.get("index"),
                "code" : we.get("code"),
                "msg"  : we.get("errmsg", str(we)),
            })

    return inserted, modified, len(errors), errors


# ═════════════════════════════════════════════════════════════════════════════
#  Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    # ── Determine PDF folder ──────────────────────────────────────────────────
    if len(sys.argv) > 1:
        pdf_folder = sys.argv[1]
    else:
        # Default: a 'pdfs' subfolder next to this script
        pdf_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdfs")

    pdf_folder = os.path.abspath(pdf_folder)

    if not os.path.isdir(pdf_folder):
        print(f"\n[ERROR] Folder not found: {pdf_folder}")
        print("Usage: python bulk_import.py <path_to_pdf_folder>")
        sys.exit(1)

    pdf_files = sorted(glob.glob(os.path.join(pdf_folder, "*.pdf")))
    if not pdf_files:
        print(f"\n[ERROR] No PDF files found in: {pdf_folder}")
        sys.exit(1)

    print("\n" + "="*60)
    print("  HS Code Bulk Importer")
    print(f"  Folder : {pdf_folder}")
    print(f"  PDFs   : {len(pdf_files)} file(s) found")
    print("="*60 + "\n")

    # ── Connect ───────────────────────────────────────────────────────────────
    try:
        col = connect_mongo()
        ensure_indexes(col)
    except Exception as e:
        print(f"\n[FATAL] Cannot connect to MongoDB: {e}")
        sys.exit(1)

    # ── Process each PDF ──────────────────────────────────────────────────────
    total_inserted  = 0
    total_modified  = 0
    total_errors    = 0
    total_skipped   = 0   # PDFs that failed to extract
    all_pdf_errors  = []

    for pdf_idx, pdf_path in enumerate(pdf_files, 1):
        fname = os.path.basename(pdf_path)
        print(f"\n[{pdf_idx}/{len(pdf_files)}] Processing: {fname}")
        print(f"  {'─'*50}")

        # ── Extract ───────────────────────────────────────────────────────────
        try:
            result = extract(pdf_path)
        except Exception as e:
            msg = f"[EXTRACT ERROR] {fname}: {e}"
            print(f"  ⚠  {msg}")
            traceback.print_exc()
            all_pdf_errors.append({"file": fname, "stage": "extract", "error": str(e)})
            total_skipped += 1
            continue

        items      = result.get("items", [])
        chapter_no = result.get("chapter", "??")

        chapter_info = {
            "chapter"            : result.get("chapter", ""),
            "chapter_description": result.get("chapter_description", ""),
            "chapter_exceptions" : result.get("chapter_exceptions", []),
        }

        if not items:
            print(f"  ⚠  No HS code items found in this PDF — skipping.")
            all_pdf_errors.append({"file": fname, "stage": "extract", "error": "No items found"})
            total_skipped += 1
            continue

        print(f"  Chapter : {chapter_no}")
        print(f"  Items   : {len(items)} HS codes extracted")

        # ── Build documents ───────────────────────────────────────────────────
        docs = []
        for item in items:
            try:
                doc = build_document(item, chapter_info, fname)
                docs.append(doc)
            except Exception as e:
                print(f"  ⚠  [BUILD ERROR] hs_code={item.get('hs_code','?')}: {e}")
                all_pdf_errors.append({
                    "file"   : fname,
                    "hs_code": item.get("hs_code", "?"),
                    "stage"  : "build",
                    "error"  : str(e),
                })

        # ── Upsert to MongoDB ─────────────────────────────────────────────────
        print(f"  Uploading {len(docs)} documents to MongoDB...", end=" ", flush=True)
        try:
            ins, mod, err_count, err_details = upsert_items(col, docs)
            print(f"Done")
            print(f"  ✔  Inserted: {ins}  |  Updated: {mod}  |  Errors: {err_count}")
            total_inserted += ins
            total_modified += mod
            total_errors   += err_count

            if err_details:
                print(f"  ⚠  Upload errors for {fname}:")
                for e in err_details:
                    print(f"       Doc #{e['index']}: [{e['code']}] {e['msg']}")
                    all_pdf_errors.append({
                        "file" : fname,
                        "stage": "upload",
                        "error": e['msg'],
                    })

        except Exception as e:
            print(f"FAILED")
            print(f"  ✖  [UPLOAD ERROR] {fname}: {e}")
            traceback.print_exc()
            all_pdf_errors.append({"file": fname, "stage": "upload", "error": str(e)})
            total_skipped += 1

    # ── Final Summary ─────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("  IMPORT COMPLETE — SUMMARY")
    print("="*60)
    print(f"  PDFs processed : {len(pdf_files) - total_skipped} / {len(pdf_files)}")
    print(f"  PDFs skipped   : {total_skipped}  (extract/upload failure)")
    print(f"  Docs inserted  : {total_inserted}  (new HS codes)")
    print(f"  Docs updated   : {total_modified}  (existing HS codes refreshed)")
    print(f"  Errors         : {total_errors}")
    print()

    if all_pdf_errors:
        print("  ── Error Details ─────────────────────────────────────")
        for err in all_pdf_errors:
            stage = err.get("stage", "?")
            file  = err.get("file", "?")
            hs    = err.get("hs_code", "")
            msg   = err.get("error", "")
            hs_str = f"  hs={hs}" if hs else ""
            print(f"  [{stage.upper()}] {file}{hs_str} → {msg}")

        # Save error log to JSON file
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "import_errors.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(all_pdf_errors, f, indent=2, ensure_ascii=False)
        print(f"\n  Error log saved → {log_path}")
    else:
        print("  No errors encountered.")

    print("="*60 + "\n")


if __name__ == "__main__":
    main()
