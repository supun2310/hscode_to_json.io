"""
HS Code PDF Extractor - Core Logic
Sri Lanka Tariff Guide PDF format:
  Col 0: HS Hdg       (e.g. 84.01)
  Col 1: HS Code      (e.g. 8401.10 / 8407.31.10)
  Col 2: Dash         (- / -- / ---)
  Col 3: Description
  Col 4: Unit
  Col 5+: Tax columns (ICL/SLSI, Preferential AP-SG, Gen Duty,
                        VAT, PAL Gen, PAL SG, Cess GEN, Cess SG,
                        Surcharge/SPD, SSCL, SCL …)
"""

import re
import os
import pdfplumber

# ── HS Code patterns ──────────────────────────────────────────────────────────
HDG_RE    = re.compile(r'^(\d{2})\.(\d{2})$')
CODE6_RE  = re.compile(r'^(\d{4})\.(\d{2})$')
CODE8_RE  = re.compile(r'^(\d{4})\.(\d{2})\.(\d{2})$')
CODE10_RE = re.compile(r'^(\d{4})\.(\d{2})\.(\d{2})\.(\d{2})$')
RAW6_RE   = re.compile(r'^\d{6}$')
RAW8_RE   = re.compile(r'^\d{8}$')
RAW10_RE  = re.compile(r'^\d{10}$')
CHAPTER_RE = re.compile(r'chapter\s+0*(\d+)', re.I)
DASH_RE    = re.compile(r'^(-+)')

# ── Preferential agreement country keys (in column order) ────────────────────
PREF_KEYS = ['ap', 'ad', 'bn', 'gt', 'in', 'pk', 'sa', 'sf', 'sd', 'sg']


# ── Basic helpers ─────────────────────────────────────────────────────────────

def normalise_code(raw: str) -> str:
    r = raw.strip()
    if RAW6_RE.match(r):  return f"{r[:4]}.{r[4:]}"
    if RAW8_RE.match(r):  return f"{r[:4]}.{r[4:6]}.{r[6:]}"
    if RAW10_RE.match(r): return f"{r[:4]}.{r[4:6]}.{r[6:8]}.{r[8:]}"
    return r

def is_leaf_code(code: str) -> bool:
    c = normalise_code(code)
    return bool(CODE6_RE.match(c) or CODE8_RE.match(c) or CODE10_RE.match(c))

def is_heading_code(code: str) -> bool:
    return bool(HDG_RE.match(code.strip()))

def fmt_heading(hs: str) -> str:
    d = hs.replace(".", "")
    return f"{d[:2]}.{d[2:4]}"

def dash_level(dash_str: str) -> int:
    return dash_str.strip().count('-') if dash_str else 0

def clean_desc(text: str) -> str:
    t = (text or "").replace("\n", " ").strip()
    t = re.sub(r'\s+', ' ', t)
    t = t.rstrip(': ').strip()
    return t

def normalise_unit(u: str) -> str:
    return (u or "").strip()

def norm_cell(cell) -> str:
    """Normalise a table cell: collapse whitespace, strip."""
    s = str(cell or '').replace('\n', ' ').strip()
    return re.sub(r'\s+', ' ', s)


# ── Tax value cleaning ────────────────────────────────────────────────────────

def clean_tax(v) -> str | None:
    """Return None for blank/dash cells, else the cleaned string."""
    if v is None:
        return None
    s = re.sub(r'\s+', ' ', str(v).replace('\n', ' ')).strip()
    if not s or s.lower() in ('-', '–', '—', 'none', 'nil', 'n/a', ''):
        return None
    return s


# ── Structural column detection ───────────────────────────────────────────────

def detect_struct_cols(table: list) -> dict:
    """
    Scan header rows to find the actual column indices for the fixed structural
    fields: hs_hdg, hs_code, dash, description, unit.

    Most chapters:
      col[0]=HS Hdg, col[1]=HS Code, col[2]=Dash, col[3]=Description, col[4]=Unit

    Chapter 20 and similar (extra merged blank before HS Code):
      col[0]=HS Hdg, col[1]=blank, col[2]=HS Code, col[3]=Dash, col[4]=Description, col[5]=Unit

    Strategy: look for 'hs code' / 'hs hdg' / 'description' / 'unit' in header
    rows.  Fall back to the classic offsets if headers are absent.
    """
    struct = {
        'hdg_col' : 0,   # HS Hdg
        'code_col': 1,   # HS Code
        'dash_col': 2,   # Dash
        'desc_col': 3,   # Description
        'unit_col': 4,   # Unit
    }

    for row in table[:7]:
        if not row:
            continue
        for idx, cell in enumerate(row):
            low = norm_cell(cell).lower()
            if not low:
                continue
            if re.match(r'hs\s*code', low):
                struct['code_col'] = idx
                struct['dash_col'] = idx + 1
                struct['desc_col'] = idx + 2
                struct['unit_col'] = idx + 3
            elif re.match(r'hs\s*hdg|hs\s*heading', low):
                struct['hdg_col'] = idx
            elif re.match(r'description|article', low):
                struct['desc_col'] = idx
                if idx > 0 and struct.get('code_col', 1) < idx:
                    struct['unit_col'] = idx + 1
            elif low == 'unit':
                struct['unit_col'] = idx

    return struct


# ── Tax column detection ──────────────────────────────────────────────────────

def detect_tax_col_map(table: list) -> dict:
    """
    Scan the first 7 rows of a pdfplumber table to find tax column indices.

    The Sri Lanka tariff PDF header (2 rows):
      Row A: … | ICL/SLSI | Preferential Duty | Gen Duty | VAT | PAL | | Cess | | Excise | SSCL | SCL
      Row B: … |          | AP AD BN GT IN PK SA SF SD SG |       |     | Gen SG |     |      |       |      |

    Returns a mapping e.g.:
      { 'ap':6, 'ad':7, ..., 'sg':15, 'general_duty':16,
        'vat':17, 'pal':18, 'pal_sg':19, 'cess':20, 'cess_sg': ?,
        'excise_spd':21, 'sscl':22 }
    """
    col_map: dict = {}
    sg_idx_list   = []   # every col index where header cell == 'sg'
    gen_idx_list  = []   # every col index where header cell == 'gen'

    # Track group header positions (first header row)
    pal_col_range_start   = None   # first col of PAL group
    cess_col_range_start  = None   # first col of Cess group

    single_keys = {'ap', 'ad', 'bn', 'gt', 'pk', 'sa', 'sf', 'sd'}

    for row_idx, row in enumerate(table[:7]):
        if not row:
            continue
        for idx, cell in enumerate(row):
            low = norm_cell(cell).lower()
            if not low or low == 'none':
                continue

            # ── Preferential country codes ────────────────────────────────
            if low in single_keys:
                col_map.setdefault(low, idx)

            elif low == 'in':
                col_map.setdefault('in', idx)

            elif low == 'sg':
                sg_idx_list.append(idx)

            # ── Gen (sub-header under Gen Duty / PAL / Cess) ─────────────
            elif low == 'gen':
                gen_idx_list.append(idx)

            # ── Gen Duty / General Duty combined cell ─────────────────────
            elif re.match(r'gen\.?\s*duty|general\s*duty', low):
                col_map.setdefault('general_duty', idx)

            # ── Group headers – record their column to resolve sub-headers ─
            elif re.match(r'^pal$', low):
                pal_col_range_start = idx

            elif re.match(r'^cess$', low):
                cess_col_range_start = idx

            # ── VAT ───────────────────────────────────────────────────────
            elif low == 'vat':
                col_map.setdefault('vat', idx)

            # ── SSCL ─────────────────────────────────────────────────────
            elif low == 'sscl':
                col_map.setdefault('sscl', idx)

            # ── SCL ───────────────────────────────────────────────────────
            elif re.match(r'^s\s*c\s*l$', low):
                col_map.setdefault('scl', idx)

            # ── Surcharge on Customs Duty / Excise / SPD ──────────────────
            elif re.search(r'surcharge|excise|spd', low):
                col_map.setdefault('excise_spd', idx)

    # ── Assign SG occurrences (in order: pref SG → PAL SG → Cess SG) ─────
    for i, idx in enumerate(sg_idx_list):
        if i == 0:
            col_map.setdefault('sg', idx)
        elif i == 1:
            col_map['pal_sg'] = idx
        elif i == 2:
            col_map['cess_sg'] = idx

    # ── Assign Gen occurrences using group header positions ───────────────
    # Strategy:
    #   - 'gen' that appears BEFORE (or at) pal_col_range_start → General Duty
    #   - 'gen' that appears WITHIN PAL group → pal
    #   - 'gen' that appears WITHIN Cess group → cess
    # Fallback when group positions are unknown: use order.
    for gen_col in gen_idx_list:
        if pal_col_range_start is not None and cess_col_range_start is not None:
            if gen_col < pal_col_range_start:
                col_map.setdefault('general_duty', gen_col)
            elif pal_col_range_start <= gen_col < cess_col_range_start:
                col_map.setdefault('pal', gen_col)
            else:
                col_map.setdefault('cess', gen_col)
        elif pal_col_range_start is not None:
            if gen_col < pal_col_range_start:
                col_map.setdefault('general_duty', gen_col)
            else:
                col_map.setdefault('pal', gen_col)
        else:
            # No group headers found – assign by order
            if 'general_duty' not in col_map:
                col_map['general_duty'] = gen_col
            elif 'pal' not in col_map:
                col_map['pal'] = gen_col
            else:
                col_map.setdefault('cess', gen_col)

    # ── Fallback: if cess not mapped but pal_sg is known, cess = pal_sg+1 ─
    if 'cess' not in col_map and 'pal_sg' in col_map:
        cess_candidate = col_map['pal_sg'] + 1
        col_map['cess'] = cess_candidate

    return col_map


def extract_taxation(row: list, col_map: dict) -> dict | None:
    """
    Build the taxation_details dict for one HS code row.
    Returns None if col_map is empty (table has no tax columns).
    """
    if not col_map:
        return None

    def g(key):
        idx = col_map.get(key)
        if idx is None or idx >= len(row):
            return None
        return clean_tax(row[idx])

    pref = {k: g(k) for k in PREF_KEYS}

    td = {
        'general_duty': g('general_duty'),
        'vat'         : g('vat'),
        'pal'         : g('pal'),
        'cess'        : g('cess'),
        'excise_spd'  : g('excise_spd'),
        'sscl'        : g('sscl'),
        'preferential_agreements': pref,
    }

    # Return None only if literally everything is None
    core_has_value = any(
        v is not None for k, v in td.items() if k != 'preferential_agreements'
    )
    pref_has_value = any(v is not None for v in pref.values())

    return td if (core_has_value or pref_has_value) else None


# ── Chapter / exception parsing ───────────────────────────────────────────────

def parse_chapter_info(page_texts: list) -> tuple:
    chapter_no = ""
    chapter_desc = ""
    exceptions = []

    for text in page_texts[:3]:
        all_lines = [(l.strip()) for l in (text or "").splitlines()]
        lines = [l for l in all_lines if l]

        for i, line in enumerate(lines):
            m = CHAPTER_RE.search(line)
            if m and not chapter_no:
                chapter_no = m.group(1).zfill(2)
                for j in range(i + 1, min(i + 6, len(lines))):
                    nxt = lines[j]
                    if nxt and not CHAPTER_RE.search(nxt) and len(nxt) > 3:
                        chapter_desc = nxt
                        break

        in_notes = False
        blank_streak = 0
        for line in all_lines:
            if re.match(r'^Notes?\s*[\.\:]?\s*$', line, re.I):
                in_notes = True
                blank_streak = 0
                continue

            if in_notes:
                if line == "":
                    blank_streak += 1
                    if blank_streak >= 2:
                        in_notes = False
                    continue
                else:
                    blank_streak = 0

                if re.match(r'^(Chapter|Section|Tariff|Subheading|Heading)\b', line, re.I):
                    in_notes = False
                    continue

                if re.match(r'^(\d+[\.\-\)]\s|\([a-zA-Z]\)\s|[-–•]\s?)', line):
                    exc = re.sub(r'^[\d\.\-\)\(\s]+', '', line).strip()
                    if exc and len(exc) > 5:
                        exceptions.append(exc)
                elif exceptions and not re.match(r'^[A-Z]', line):
                    exceptions[-1] = exceptions[-1] + " " + line

    return chapter_no, chapter_desc, exceptions


# ── Row processor ─────────────────────────────────────────────────────────────

def process_table(table: list, items: list, state: dict):
    """
    Process one pdfplumber table.

    Column layout is auto-detected via detect_struct_cols() so that both the
    classic layout (HS Code at col 1) and the shifted layout used in Chapter 20
    (HS Code at col 2, extra blank column before it) are handled correctly.

    state keys:
      heading      : '84.01'
      heading_desc : '...'
      stack        : {level: description}
    """
    # Auto-detect structural column positions (hdg, code, dash, desc, unit)
    sc = detect_struct_cols(table)
    hdg_c  = sc['hdg_col']
    code_c = sc['code_col']
    dash_c = sc['dash_col']
    desc_c = sc['desc_col']
    unit_c = sc['unit_col']

    # Detect tax columns for this specific table
    col_map = detect_tax_col_map(table)

    min_cols = max(hdg_c, code_c, dash_c, desc_c) + 1

    for row in table:
        if not row or len(row) < min_cols:
            continue

        hdg_cell  = str(row[hdg_c]  or '').strip()
        code_cell = str(row[code_c] or '').strip()
        dash_cell = str(row[dash_c] or '').strip()
        desc_raw  = str(row[desc_c] or '')
        unit_cell = normalise_unit(str(row[unit_c] or '')) if len(row) > unit_c else ''

        desc_cell = clean_desc(desc_raw)

        # Skip header rows
        if hdg_cell.upper() in ('HS HDG', 'HS CODE', 'HEADING'):
            continue
        if code_cell.upper() in ('HS CODE',):
            continue
        if desc_cell.upper() in ('DESCRIPTION', 'ARTICLE'):
            continue
        if not desc_cell:
            continue

        # ── Heading row (e.g. "84.01" or "20.01") ────────────────────────
        if is_heading_code(hdg_cell):
            state['heading']      = hdg_cell
            state['heading_desc'] = desc_cell
            state['stack']        = {0: desc_cell}
            continue

        nc    = normalise_code(code_cell) if code_cell else ''
        level = dash_level(dash_cell)

        # ── Leaf row (has HS code) ─────────────────────────────────────────
        if nc and is_leaf_code(nc):
            stack        = state.get('stack', {})
            heading      = state.get('heading', fmt_heading(nc) if nc else '')
            heading_desc = state.get('heading_desc', '')

            path_parts = [stack.get(0, heading_desc)]
            for lvl in range(1, level):
                if lvl in stack:
                    path_parts.append(stack[lvl])
            path_parts.append(desc_cell)

            h_level = len(path_parts) - 1
            h_path  = ' > '.join(path_parts)
            f_ctx   = ': '.join(path_parts)

            # ── Extract tax data from this row ─────────────────────────────
            tax = extract_taxation(row, col_map)

            items.append({
                'hs_code'                 : nc,
                'heading'                 : heading,
                'heading_description'     : heading_desc,
                'hierarchical_level'      : h_level,
                'hierarchy_path'          : h_path,
                'self_description'        : desc_cell,
                'full_context_description': f_ctx,
                'unit'                    : unit_cell,
                'taxation_details'        : tax,
            })

            # Update stack so deeper sub-codes can use this as parent
            if level > 0:
                state['stack'][level] = desc_cell
                for k in list(state['stack'].keys()):
                    if k > level:
                        del state['stack'][k]

        # ── Intermediate row (no HS code, has dashes) ──────────────────────
        elif not nc and desc_cell and level > 0:
            state['stack'][level] = desc_cell
            for k in list(state['stack'].keys()):
                if k > level:
                    del state['stack'][k]


# ── Main entry point ──────────────────────────────────────────────────────────

def extract(pdf_path: str) -> dict:
    filename = os.path.basename(pdf_path)
    result = {
        'file_reference'     : filename,
        'chapter'            : '',
        'chapter_description': '',
        'chapter_exceptions' : [],
        'items'              : [],
    }

    items: list = []
    state: dict = {'heading': '', 'heading_desc': '', 'stack': {}}
    page_texts: list = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ''
            page_texts.append(text)
            tables = page.extract_tables() or []
            for table in tables:
                if table:
                    process_table(table, items, state)

    chap_no, chap_desc, exceptions = parse_chapter_info(page_texts)

    if not chap_no and items:
        chap_no = items[0]['hs_code'].replace('.', '')[:2]

    result['chapter']             = chap_no
    result['chapter_description'] = chap_desc
    result['chapter_exceptions']  = exceptions
    result['items']               = items
    return result
