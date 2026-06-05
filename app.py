"""
HS Code PDF → JSON Web Tool
Run: py app.py   then open http://localhost:5000
"""

import os, sys, json, glob, traceback, tempfile, threading
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template_string, Response, stream_with_context
from extractor import extract

# ── MongoDB ──────────────────────────────────────────────────────────────────
try:
    from pymongo import MongoClient, UpdateOne
    from pymongo.server_api import ServerApi
    MONGO_AVAILABLE = True
except ImportError:
    MONGO_AVAILABLE = False

MONGO_URI = "mongodb+srv://udanaravindurv_db_user:RqWgEd8CMHxb5Ttp@cluster0.huccgsz.mongodb.net/?appName=Cluster0"
DB_NAME   = "wizard"
COL_NAME  = "hscodes"

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HS Code PDF &rarr; JSON Extractor</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

  :root{
    --bg:#0d0f14; --surface:#141720; --surface2:#1c2030;
    --border:#2a2f45; --accent:#6c63ff; --accent2:#00d4aa;
    --text:#e2e8f0; --muted:#64748b; --danger:#ff4d6d;
    --success:#22c55e; --warn:#f59e0b;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;min-height:100vh;display:flex;flex-direction:column}

  /* Header */
  header{padding:24px 40px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:14px;
         background:linear-gradient(135deg,#141720 0%,#1a1f30 100%)}
  .logo{width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg,var(--accent),var(--accent2));
        display:flex;align-items:center;justify-content:center;font-size:20px}
  header h1{font-size:1.25rem;font-weight:600;letter-spacing:-.5px}
  header p{font-size:.8rem;color:var(--muted);margin-top:2px}

  main{flex:1;display:grid;grid-template-columns:420px 1fr;gap:0;height:calc(100vh - 73px)}

  /* Left panel */
  .panel-left{background:var(--surface);border-right:1px solid var(--border);padding:32px 28px;
              display:flex;flex-direction:column;gap:24px;overflow-y:auto}

  /* Drop zone */
  .dropzone{border:2px dashed var(--border);border-radius:16px;padding:40px 24px;text-align:center;
            cursor:pointer;transition:all .25s;position:relative;background:var(--surface2)}
  .dropzone:hover,.dropzone.drag{border-color:var(--accent);background:rgba(108,99,255,.07)}
  .dropzone input{position:absolute;inset:0;opacity:0;cursor:pointer}
  .dropzone .icon{font-size:2.5rem;margin-bottom:12px}
  .dropzone h3{font-size:.95rem;font-weight:500;margin-bottom:6px}
  .dropzone p{font-size:.78rem;color:var(--muted)}
  .dropzone .file-name{margin-top:12px;font-size:.82rem;color:var(--accent);font-weight:500;
                        background:rgba(108,99,255,.1);padding:6px 12px;border-radius:8px;display:none}

  /* Options */
  .options{display:flex;flex-direction:column;gap:14px}
  .options label{font-size:.82rem;color:var(--muted);font-weight:500;display:block;margin-bottom:5px}
  .options input,.options select{width:100%;background:var(--surface2);border:1px solid var(--border);
    color:var(--text);padding:9px 12px;border-radius:8px;font-family:inherit;font-size:.85rem;outline:none;
    transition:border-color .2s}
  .options input:focus,.options select:focus{border-color:var(--accent)}

  /* Button */
  .btn-extract{width:100%;padding:14px;border:none;border-radius:12px;cursor:pointer;
               background:linear-gradient(135deg,var(--accent),#8b5cf6);color:#fff;
               font-size:.95rem;font-weight:600;letter-spacing:.3px;transition:all .25s;
               display:flex;align-items:center;justify-content:center;gap:8px}
  .btn-extract:hover{transform:translateY(-1px);box-shadow:0 8px 24px rgba(108,99,255,.4)}
  .btn-extract:disabled{opacity:.5;cursor:not-allowed;transform:none;box-shadow:none}

  /* Status */
  .status{font-size:.82rem;padding:10px 14px;border-radius:8px;display:none}
  .status.error{background:rgba(255,77,109,.1);border:1px solid rgba(255,77,109,.3);color:var(--danger);display:block}
  .status.success{background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.3);color:var(--success);display:block}
  .status.info{background:rgba(108,99,255,.1);border:1px solid rgba(108,99,255,.3);color:var(--accent);display:block}

  /* Stats */
  .stats{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .stat-card{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:14px;text-align:center}
  .stat-card .num{font-size:1.5rem;font-weight:700;color:var(--accent2)}
  .stat-card .lbl{font-size:.72rem;color:var(--muted);margin-top:3px}

  /* Right panel */
  .panel-right{display:flex;flex-direction:column;background:var(--bg)}
  .output-header{padding:16px 24px;border-bottom:1px solid var(--border);display:flex;
                  align-items:center;justify-content:space-between;background:var(--surface)}
  .output-header h2{font-size:.9rem;font-weight:600;color:var(--muted)}
  .output-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .btn-sm{padding:7px 14px;border-radius:8px;border:1px solid var(--border);background:var(--surface2);
          color:var(--text);font-size:.8rem;font-weight:500;cursor:pointer;transition:all .2s;
          display:flex;align-items:center;gap:6px}
  .btn-sm:hover{border-color:var(--accent);color:var(--accent)}
  .btn-sm.copied{border-color:var(--success);color:var(--success)}
  .btn-sm.active{border-color:var(--accent);background:rgba(108,99,255,.18);color:var(--accent)}

  .output-area{flex:1;overflow:auto;padding:20px 24px}
  pre#json-output{font-family:'JetBrains Mono',monospace;font-size:.78rem;line-height:1.65;
                   white-space:pre-wrap;word-break:break-word;color:#abb2bf}

  /* Syntax highlight */
  .jk{color:#e06c75}
  .js{color:#98c379}
  .jn{color:#d19a66}
  .jb{color:#56b6c2}

  /* Placeholder */
  .placeholder{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;
                gap:16px;color:var(--muted)}
  .placeholder .big{font-size:4rem;opacity:.25}
  .placeholder p{font-size:.85rem;max-width:300px;text-align:center;line-height:1.6}

  /* Spinner */
  @keyframes spin{to{transform:rotate(360deg)}}
  .spinner{width:18px;height:18px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;
            border-radius:50%;animation:spin .7s linear infinite}

  /* Scrollbar */
  ::-webkit-scrollbar{width:5px;height:5px}
  ::-webkit-scrollbar-track{background:transparent}
  ::-webkit-scrollbar-thumb{background:var(--border);border-radius:99px}

  /* ── TAX DETAILS PANEL ────────────────────────────────────── */

  .tax-view{display:flex;flex-direction:column;height:100%}

  .hs-banner{padding:18px 22px;background:linear-gradient(135deg,rgba(108,99,255,.13),rgba(0,212,170,.07));
             border-radius:14px}
  .hs-code-badge{display:inline-flex;align-items:center;gap:8px;margin-bottom:8px}
  .hs-badge{font-family:'JetBrains Mono',monospace;font-size:1.1rem;font-weight:700;
            background:linear-gradient(135deg,var(--accent),var(--accent2));
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
  .unit-badge{background:rgba(108,99,255,.15);border:1px solid rgba(108,99,255,.3);
              color:var(--accent);font-size:.72rem;padding:3px 9px;border-radius:20px;font-weight:600}
  .hs-banner h2{font-size:1rem;font-weight:600;line-height:1.4;margin-bottom:5px}
  .breadcrumb{font-size:.74rem;color:var(--muted);display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-top:4px}
  .breadcrumb-sep{opacity:.35}

  .section-title{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;
                 color:var(--muted);margin-bottom:11px;display:flex;align-items:center;gap:8px}
  .section-title::after{content:'';flex:1;height:1px;background:var(--border)}

  /* Duty cards */
  .duty-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:11px}
  .duty-card{background:var(--surface2);border:1px solid var(--border);border-radius:13px;
             padding:15px 14px;position:relative;overflow:hidden;transition:transform .2s,border-color .2s}
  .duty-card:hover{transform:translateY(-2px)}
  .duty-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:2px}
  .duty-card.free::before{background:linear-gradient(90deg,#00d4aa,#00ffcc)}
  .duty-card.paid::before{background:linear-gradient(90deg,#f59e0b,#ff9f0a)}
  .duty-card.exempt::before{background:linear-gradient(90deg,#6c63ff,#8b5cf6)}
  .duty-card.na::before{background:var(--border)}
  .duty-card:hover.free{border-color:rgba(0,212,170,.4)}
  .duty-card:hover.paid{border-color:rgba(245,158,11,.4)}
  .duty-card:hover.exempt{border-color:rgba(108,99,255,.4)}
  .dc-label{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:7px}
  .dc-value{font-size:1.2rem;font-weight:700;line-height:1}
  .dc-desc{font-size:.67rem;color:var(--muted);margin-top:5px}
  .dc-value.free{color:#00d4aa}
  .dc-value.paid{color:#f59e0b}
  .dc-value.exempt{color:#6c63ff}
  .dc-value.na{color:var(--muted)}

  /* Summary strip */
  .tax-summary{background:linear-gradient(135deg,rgba(108,99,255,.08),rgba(0,212,170,.05));
               border:1px solid rgba(108,99,255,.2);border-radius:13px;padding:14px 18px;
               display:flex;align-items:center;gap:14px;flex-wrap:wrap}
  .summary-item{display:flex;flex-direction:column;gap:3px;flex:1;min-width:90px}
  .s-label{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--muted)}
  .s-value{font-size:.88rem;font-weight:700}
  .sum-div{width:1px;height:34px;background:var(--border)}

  /* Preferential agreements */
  .pref-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(128px,1fr));gap:8px}
  .pref-item{background:var(--surface2);border:1px solid var(--border);border-radius:10px;
             padding:10px 13px;display:flex;align-items:center;justify-content:space-between;
             transition:border-color .2s}
  .pref-item:hover{border-color:var(--accent)}
  .pref-country{display:flex;flex-direction:column;gap:2px}
  .pref-code{font-size:.67rem;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--muted)}
  .pref-name{font-size:.7rem;color:var(--text)}
  .pref-rate{font-size:.82rem;font-weight:700}
  .pref-rate.free{color:#00d4aa}
  .pref-rate.paid{color:#f59e0b}
  .pref-rate.na{color:var(--border);font-weight:400}

  /* Item browser */
  .item-browser{padding:11px 22px;background:var(--surface);border-bottom:1px solid var(--border);
                display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  .item-browser select{background:var(--surface2);border:1px solid var(--border);color:var(--text);
    padding:6px 10px;border-radius:8px;font-size:.78rem;font-family:inherit;outline:none;flex:1;max-width:420px}
  .item-browser select:focus{border-color:var(--accent)}
  .browser-label{font-size:.73rem;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.8px;white-space:nowrap}

  .view-tabs{display:flex;gap:6px}

  /* ── IMPORT PANEL ──────────────────────────────────────────── */
  .panel-tabs{display:flex;gap:0;border-bottom:1px solid var(--border);margin:-32px -28px 24px;
              padding:0 28px;background:var(--surface)}
  .panel-tab{padding:13px 18px;font-size:.82rem;font-weight:600;cursor:pointer;color:var(--muted);
             border-bottom:2px solid transparent;transition:all .2s;background:none;border-top:none;
             border-left:none;border-right:none;white-space:nowrap}
  .panel-tab.active{color:var(--accent);border-bottom-color:var(--accent)}
  .panel-tab:hover:not(.active){color:var(--text)}

  .import-panel{display:flex;flex-direction:column;gap:16px}
  .import-panel label{font-size:.82rem;color:var(--muted);font-weight:500;display:block;margin-bottom:5px}
  .import-panel input[type=text]{width:100%;background:var(--surface2);border:1px solid var(--border);
    color:var(--text);padding:9px 12px;border-radius:8px;font-family:inherit;font-size:.85rem;outline:none;
    transition:border-color .2s}
  .import-panel input:focus{border-color:var(--accent)}
  .btn-import{width:100%;padding:13px;border:none;border-radius:12px;cursor:pointer;
              background:linear-gradient(135deg,#00d4aa,#00a88a);color:#000;
              font-size:.9rem;font-weight:700;letter-spacing:.3px;transition:all .25s;
              display:flex;align-items:center;justify-content:center;gap:8px}
  .btn-import:hover{transform:translateY(-1px);box-shadow:0 8px 24px rgba(0,212,170,.35)}
  .btn-import:disabled{opacity:.5;cursor:not-allowed;transform:none;box-shadow:none}

  /* Upload single PDF button */
  .btn-upload{width:100%;padding:13px;border:none;border-radius:12px;cursor:pointer;
              background:linear-gradient(135deg,var(--accent),#8b5cf6);color:#fff;
              font-size:.9rem;font-weight:700;letter-spacing:.3px;transition:all .25s;
              display:flex;align-items:center;justify-content:center;gap:8px}
  .btn-upload:hover{transform:translateY(-1px);box-shadow:0 8px 24px rgba(108,99,255,.4)}
  .btn-upload:disabled{opacity:.5;cursor:not-allowed;transform:none;box-shadow:none}

  /* Safe-upsert info banner */
  .safe-banner{background:rgba(0,212,170,.07);border:1px solid rgba(0,212,170,.22);
               border-radius:10px;padding:10px 14px;font-size:.77rem;color:var(--accent2);line-height:1.5}

  /* Progress log */
  .import-log{background:var(--surface2);border:1px solid var(--border);border-radius:10px;
              max-height:220px;overflow-y:auto;padding:10px;display:none;flex-direction:column;gap:4px}
  .log-row{font-size:.75rem;font-family:'JetBrains Mono',monospace;padding:3px 6px;border-radius:5px;
            display:flex;align-items:flex-start;gap:6px;line-height:1.4}
  .log-row.info   {color:var(--accent)}
  .log-row.success{color:var(--success)}
  .log-row.warn   {color:var(--warn)}
  .log-row.error  {color:var(--danger);background:rgba(255,77,109,.06)}
  .log-row.done   {color:var(--muted)}
  .log-icon{flex-shrink:0;width:14px;text-align:center}

  /* Import stats */
  .import-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;display:none}
  .import-stats .stat-card .num{font-size:1.2rem}
</style>
</head>
<body>
<header>
  <div class="logo">&#x1F4E6;</div>
  <div>
    <h1>HS Code PDF &rarr; JSON Extractor</h1>
    <p>Upload a tariff PDF and get structured JSON with full taxation details</p>
  </div>
</header>

<main>
  <!-- Left panel with tabs -->
  <div class="panel-left">
    <!-- Tab switcher -->
    <div class="panel-tabs">
      <button class="panel-tab active" id="tab-extract" onclick="switchPanel('extract')">&#x1F4C4; Extract PDF</button>
      <button class="panel-tab" id="tab-import" onclick="switchPanel('import')">&#x1F5C4;&#xFE0F; Import to DB</button>
      <button class="panel-tab" id="tab-upload" onclick="switchPanel('upload')">&#x2B06;&#xFE0F; Upload to DB</button>
    </div>

    <!-- Extract Panel -->
    <div id="panel-extract">
      <div class="dropzone" id="dropzone">
        <input type="file" id="file-input" accept=".pdf">
        <div class="icon">&#x1F4C4;</div>
        <h3>Drop your PDF here</h3>
        <p>or click to browse</p>
        <div class="file-name" id="file-name"></div>
      </div>

      <div class="options">
        <div>
          <label>Chapter Override (optional)</label>
          <input type="text" id="opt-chapter" placeholder="e.g. 01" maxlength="2">
        </div>
        <div>
          <label>File Reference Label</label>
          <input type="text" id="opt-fileref" placeholder="Auto-detected from filename">
        </div>
      </div>

      <button class="btn-extract" id="btn-extract" onclick="doExtract()">
        <span id="btn-text">&#x26A1; Extract JSON</span>
      </button>

      <div class="status" id="status"></div>

      <div class="stats" id="stats" style="display:none">
        <div class="stat-card"><div class="num" id="stat-items">0</div><div class="lbl">HS Codes</div></div>
        <div class="stat-card"><div class="num" id="stat-exc">0</div><div class="lbl">Exceptions</div></div>
        <div class="stat-card"><div class="num" id="stat-chap">-</div><div class="lbl">Chapter</div></div>
        <div class="stat-card"><div class="num" id="stat-lvls">-</div><div class="lbl">Max Depth</div></div>
      </div>
    </div>

    <!-- Import Panel -->
    <div id="panel-import" class="import-panel" style="display:none">
      <div>
        <label>PDF Folder Path</label>
        <input type="text" id="import-folder"
          placeholder="e.g. C:\Users\you\pdfs or /home/user/pdfs">
      </div>

      <button class="btn-import" id="btn-import" onclick="doImport()">
        <span id="import-btn-text">&#x1F680; Start Bulk Import</span>
      </button>

      <div class="status" id="import-status"></div>

      <!-- Live log -->
      <div class="import-log" id="import-log"></div>

      <!-- Result stats -->
      <div class="import-stats" id="import-stats">
        <div class="stat-card"><div class="num" id="imp-ins">0</div><div class="lbl">Inserted</div></div>
        <div class="stat-card"><div class="num" id="imp-mod">0</div><div class="lbl">Updated</div></div>
        <div class="stat-card"><div class="num" id="imp-err">0</div><div class="lbl">Errors</div></div>
      </div>
    </div>

    <!-- ── Upload Single PDF Panel ────────────────────────────────────── -->
    <div id="panel-upload" class="import-panel" style="display:none">

      <div class="dropzone" id="upload-dropzone" style="padding:26px 20px">
        <input type="file" id="upload-file-input" accept=".pdf">
        <div class="icon">&#x2B06;&#xFE0F;</div>
        <h3>Drop PDF here to upload</h3>
        <p>or click to browse &mdash; one chapter at a time</p>
        <div class="file-name" id="upload-file-name"></div>
      </div>

      <div class="safe-banner">
        &#x1F6E1;&#xFE0F; <strong>Safe upsert</strong> &mdash; only inserts / updates HS codes from this
        PDF. <em>All other chapters already in the database are never changed or deleted.</em>
      </div>

      <button class="btn-upload" id="btn-upload" onclick="doUpload()">
        <span id="upload-btn-text">&#x2B06;&#xFE0F; Upload to MongoDB</span>
      </button>

      <div class="status" id="upload-status"></div>

      <!-- Live log -->
      <div class="import-log" id="upload-log"></div>

      <!-- Result stats -->
      <div class="import-stats" id="upload-stats" style="display:none">
        <div class="stat-card"><div class="num" id="upload-ins">0</div><div class="lbl">Inserted</div></div>
        <div class="stat-card"><div class="num" id="upload-mod">0</div><div class="lbl">Updated</div></div>
        <div class="stat-card"><div class="num" id="upload-err">0</div><div class="lbl">Errors</div></div>
      </div>
    </div>
  </div>

  <!-- Right: Output -->
  <div class="panel-right" id="output-panel">
    <div class="placeholder" id="placeholder">
      <div class="big">&#x1F4CB;</div>
      <p>Upload a PDF to extract HS codes as structured JSON with full taxation details</p>
    </div>
  </div>
</main>

<script>
let currentJson = null;
let selectedFile = null;
let currentView = 'tax';

const COUNTRY_NAMES = {
  ap:'Asia-Pacific', ad:'Andean Comm.', bn:'BIMSTEC',
  gt:'GSTP', 'in':'India', pk:'Pakistan',
  sa:'SAFTA', sf:'Sri Lanka-FTA', sd:'Sri Lanka-Singapore', sg:'Singapore'
};

// Drag & drop
const dz = document.getElementById('dropzone');
const fi = document.getElementById('file-input');
dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag'); });
dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
dz.addEventListener('drop', e => {
  e.preventDefault(); dz.classList.remove('drag');
  const f = e.dataTransfer.files[0];
  if (f && f.name.toLowerCase().endsWith('.pdf')) { selectedFile = f; showFileName(f.name); }
  else if (f) showStatus('Please drop a PDF file.', 'error');
});
fi.addEventListener('change', () => {
  if (fi.files && fi.files[0]) { selectedFile = fi.files[0]; showFileName(fi.files[0].name); }
});

function showFileName(name) {
  const nm = document.getElementById('file-name');
  nm.textContent = name; nm.style.display = 'block';
  const fr = document.getElementById('opt-fileref');
  if (!fr.value) fr.value = name;
  document.getElementById('status').className = 'status';
}

// Extract
async function doExtract() {
  const file = selectedFile || (fi.files && fi.files[0]);
  if (!file) { showStatus('Please select a PDF file first.', 'error'); return; }
  const btn = document.getElementById('btn-extract');
  const btnText = document.getElementById('btn-text');
  btn.disabled = true;
  btnText.innerHTML = '<div class="spinner"></div> Extracting...';
  showStatus('Processing PDF...', 'info');
  hideOutput();
  const fd = new FormData();
  fd.append('pdf', file);
  fd.append('chapter', document.getElementById('opt-chapter').value);
  fd.append('fileref', document.getElementById('opt-fileref').value || file.name);
  try {
    const res = await fetch('/extract', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Extraction failed');
    currentJson = data;
    showResult(data);
  } catch (e) {
    showStatus('Error: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btnText.innerHTML = '&#x26A1; Extract JSON';
  }
}

function showResult(data) {
  const items = data.items || [];
  const maxDepth = items.length ? Math.max(...items.map(i => i.hierarchical_level || 0)) : 0;
  document.getElementById('stat-items').textContent = items.length;
  document.getElementById('stat-exc').textContent = (data.chapter_exceptions || []).length;
  document.getElementById('stat-chap').textContent = data.chapter || '-';
  document.getElementById('stat-lvls').textContent = maxDepth;
  document.getElementById('stats').style.display = 'grid';
  renderOutputPanel(data, currentView);
  showStatus('Extracted ' + items.length + ' HS codes from chapter ' + (data.chapter || '?'), 'success');
}

function renderOutputPanel(data, view) {
  const items = data.items || [];
  const taxItem = items.find(i => i.taxation_details) || items[0] || null;
  const panel = document.getElementById('output-panel');
  panel.innerHTML =
    '<div class="output-header">' +
      '<h2>Output &mdash; ' + items.length + ' HS codes extracted</h2>' +
      '<div class="output-actions">' +
        '<div class="view-tabs">' +
          '<button class="btn-sm ' + (view==='tax'?'active':'') + '" onclick="switchView(\'tax\')">&#x1F3F7;&#xFE0F; Tax Details</button>' +
          '<button class="btn-sm ' + (view==='json'?'active':'') + '" onclick="switchView(\'json\')">{ } JSON</button>' +
        '</div>' +
        '<button class="btn-sm" id="btn-copy" onclick="copyJson()">&#x1F4CB; Copy JSON</button>' +
        '<button class="btn-sm" onclick="downloadJson()">&#x2B07; Download</button>' +
      '</div>' +
    '</div>' +
    '<div class="output-area" id="output-area">' +
      (view === 'tax' ? buildTaxView(data, taxItem) : buildJsonView(data)) +
    '</div>';
}

function switchView(v) {
  currentView = v;
  if (currentJson) renderOutputPanel(currentJson, v);
}

// ── Tax Details View ─────────────────────────────────────────────────────────
function buildTaxView(data, item) {
  if (!item) return '<div class="placeholder"><div class="big">&#x1F50D;</div><p>No items found.</p></div>';
  const td = item.taxation_details || {};
  const pref = td.preferential_agreements || {};
  const items = data.items || [];

  // Dropdown browser
  let selectorHtml = '';
  if (items.length > 1) {
    let opts = items.map((it, idx) =>
      '<option value="' + idx + '"' + (it === item ? ' selected' : '') + '>' +
      esc2(it.hs_code || '?') + ' \u2014 ' + esc2((it.self_description || it.full_context_description || '').slice(0,60)) +
      '</option>'
    ).join('');
    selectorHtml =
      '<div class="item-browser">' +
        '<span class="browser-label">Browse HS Code:</span>' +
        '<select id="item-selector" onchange="selectItem(this.value)">' + opts + '</select>' +
      '</div>';
  }

  // Duty cards definition
  const duties = [
    { key:'general_duty', label:'General Duty', value: td.general_duty },
    { key:'vat',          label:'VAT',          value: td.vat },
    { key:'pal',          label:'PAL',          value: td.pal },
    { key:'cess',         label:'Cess',         value: td.cess },
    { key:'excise_spd',   label:'Excise SPD',   value: td.excise_spd },
    { key:'sscl',         label:'SSCL',         value: td.sscl },
  ];

  function dutyClass(v) {
    if (v === null || v === undefined) return 'na';
    const s = String(v).toLowerCase();
    if (s === 'free') return 'free';
    if (s === 'ex' || s === 'exempt' || s === 'excluded') return 'exempt';
    return 'paid';
  }

  const dutyCards = duties.map(d => {
    const cls = dutyClass(d.value);
    const display = (d.value === null || d.value === undefined) ? '\u2014' : d.value;
    const desc = cls==='free' ? 'No duty applicable' : cls==='exempt' ? 'Exempt / Excluded' : cls==='na' ? 'Not applicable' : 'Rate applied';
    return '<div class="duty-card ' + cls + '">' +
      '<div class="dc-label">' + d.label + '</div>' +
      '<div class="dc-value ' + cls + '">' + esc2(String(display)) + '</div>' +
      '<div class="dc-desc">' + desc + '</div>' +
    '</div>';
  }).join('');

  // Preferential agreements
  const prefItems = Object.entries(pref).map(([code, rate]) => {
    const cls = rate === null ? 'na' : String(rate).toLowerCase() === 'free' ? 'free' : 'paid';
    const display = rate === null ? 'N/A' : rate;
    return '<div class="pref-item">' +
      '<div class="pref-country">' +
        '<span class="pref-code">' + code.toUpperCase() + '</span>' +
        '<span class="pref-name">' + esc2(COUNTRY_NAMES[code] || code) + '</span>' +
      '</div>' +
      '<span class="pref-rate ' + cls + '">' + esc2(String(display)) + '</span>' +
    '</div>';
  }).join('');

  // Summary metrics
  const effectiveRate = td.general_duty || '\u2014';
  const activePref = Object.values(pref).filter(v => v !== null).length;
  const totalDuties = duties.filter(d => d.value !== null && d.value !== undefined).length;
  const effColor = effectiveRate === 'Free' ? '#00d4aa' : effectiveRate === '\u2014' ? 'var(--muted)' : '#f59e0b';

  // Breadcrumb
  const breadcrumb = (item.hierarchy_path || '').split(' > ')
    .map(p => esc2(p))
    .join('<span class="breadcrumb-sep"> &rsaquo; </span>');

  return '<div class="tax-view">' +
    selectorHtml +
    '<div style="flex:1;overflow-y:auto;padding:20px 22px;display:flex;flex-direction:column;gap:20px">' +

      // HS Banner
      '<div class="hs-banner">' +
        '<div class="hs-code-badge">' +
          '<span class="hs-badge">' + esc2(item.hs_code || '') + '</span>' +
          (item.unit ? '<span class="unit-badge">Unit: ' + esc2(item.unit) + '</span>' : '') +
        '</div>' +
        '<h2>' + esc2(item.full_context_description || item.self_description || '') + '</h2>' +
        '<div class="breadcrumb">' + breadcrumb + '</div>' +
      '</div>' +

      // Summary strip
      '<div class="tax-summary">' +
        '<div class="summary-item"><span class="s-label">Effective Duty</span><span class="s-value" style="color:' + effColor + '">' + esc2(effectiveRate) + '</span></div>' +
        '<div class="sum-div"></div>' +
        '<div class="summary-item"><span class="s-label">Active Duties</span><span class="s-value" style="color:var(--accent)">' + totalDuties + ' / ' + duties.length + '</span></div>' +
        '<div class="sum-div"></div>' +
        '<div class="summary-item"><span class="s-label">Pref. Agreements</span><span class="s-value" style="color:var(--accent2)">' + activePref + ' active</span></div>' +
        '<div class="sum-div"></div>' +
        '<div class="summary-item"><span class="s-label">HS Level</span><span class="s-value">L' + (item.hierarchical_level || '?') + '</span></div>' +
      '</div>' +

      // Core Duties
      '<div>' +
        '<div class="section-title">&#x1F4CA; Core Duty Rates</div>' +
        '<div class="duty-grid">' + dutyCards + '</div>' +
      '</div>' +

      // Preferential Agreements
      (prefItems ? '<div>' +
        '<div class="section-title">&#x1F91D; Preferential Trade Agreements</div>' +
        '<div class="pref-grid">' + prefItems + '</div>' +
      '</div>' : '') +

    '</div>' +
  '</div>';
}

function selectItem(idx) {
  if (!currentJson) return;
  const item = (currentJson.items || [])[parseInt(idx)];
  if (!item) return;
  const area = document.getElementById('output-area');
  if (area) area.innerHTML = buildTaxView(currentJson, item);
}

// JSON view
function buildJsonView(data) {
  return '<pre id="json-output">' + highlight(JSON.stringify(data, null, 2)) + '</pre>';
}

function hideOutput() {
  document.getElementById('output-panel').innerHTML =
    '<div class="placeholder" id="placeholder"><div class="big">&#x23F3;</div><p>Extracting data from PDF&hellip;</p></div>';
  document.getElementById('stats').style.display = 'none';
}

function showStatus(msg, type) {
  const s = document.getElementById('status');
  s.textContent = msg; s.className = 'status ' + type;
}

// Copy / Download
async function copyJson() {
  if (!currentJson) return;
  await navigator.clipboard.writeText(JSON.stringify(currentJson, null, 2));
  const b = document.getElementById('btn-copy');
  b.textContent = 'Copied!'; b.classList.add('copied');
  setTimeout(() => { b.innerHTML = '&#x1F4CB; Copy JSON'; b.classList.remove('copied'); }, 2000);
}

function downloadJson() {
  if (!currentJson) return;
  const blob = new Blob([JSON.stringify(currentJson, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'chapter_' + (currentJson.chapter || '00') + '.json';
  a.click();
}

// Syntax highlighting
function highlight(json) {
  return json.replace(/(\"(\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*\"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function(match) {
    if (/^\"/.test(match)) {
      if (/:$/.test(match)) return '<span class="jk">' + esc(match) + '</span>';
      return '<span class="js">' + esc(match) + '</span>';
    }
    if (/true|false|null/.test(match)) return '<span class="jb">' + match + '</span>';
    return '<span class="jn">' + match + '</span>';
  });
}
function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function esc2(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// ── Panel tab switch ─────────────────────────────────────────────────────────
function switchPanel(name) {
  document.getElementById('panel-extract').style.display = name === 'extract' ? '' : 'none';
  document.getElementById('panel-import').style.display  = name === 'import'  ? '' : 'none';
  document.getElementById('panel-upload').style.display  = name === 'upload'  ? '' : 'none';
  document.getElementById('tab-extract').classList.toggle('active', name === 'extract');
  document.getElementById('tab-import').classList.toggle('active', name === 'import');
  document.getElementById('tab-upload').classList.toggle('active',  name === 'upload');
}

// ── Bulk Import to MongoDB ───────────────────────────────────────────────────
let importRunning = false;

// ── Single PDF Upload ────────────────────────────────────────────────────────
let uploadRunning      = false;
let selectedUploadFile = null;

const _udz = document.getElementById('upload-dropzone');
const _ufi = document.getElementById('upload-file-input');
_udz.addEventListener('dragover',  e => { e.preventDefault(); _udz.classList.add('drag'); });
_udz.addEventListener('dragleave', () => _udz.classList.remove('drag'));
_udz.addEventListener('drop', e => {
  e.preventDefault(); _udz.classList.remove('drag');
  const f = e.dataTransfer.files[0];
  if (f && f.name.toLowerCase().endsWith('.pdf')) { selectedUploadFile = f; _showUploadFile(f.name); }
  else if (f) _setUploadStatus('Please drop a PDF file.', 'error');
});
_ufi.addEventListener('change', () => {
  if (_ufi.files && _ufi.files[0]) { selectedUploadFile = _ufi.files[0]; _showUploadFile(_ufi.files[0].name); }
});

function _showUploadFile(name) {
  const nm = document.getElementById('upload-file-name');
  nm.textContent = name; nm.style.display = 'block';
  document.getElementById('upload-status').className = 'status';
}
function _logUpload(type, icon, msg) {
  const log = document.getElementById('upload-log');
  log.style.display = 'flex';
  const row = document.createElement('div');
  row.className = 'log-row ' + type;
  row.innerHTML = '<span class="log-icon">' + icon + '</span><span>' + esc2(msg) + '</span>';
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
}
function _setUploadStatus(msg, type) {
  const s = document.getElementById('upload-status');
  s.textContent = msg; s.className = 'status ' + type;
}

function logRow(type, icon, msg) {
  const log = document.getElementById('import-log');
  log.style.display = 'flex';
  const row = document.createElement('div');
  row.className = 'log-row ' + type;
  row.innerHTML = '<span class="log-icon">' + icon + '</span><span>' + esc2(msg) + '</span>';
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
}

function setImportStatus(msg, type) {
  const s = document.getElementById('import-status');
  s.textContent = msg; s.className = 'status ' + type;
}

async function doImport() {
  if (importRunning) return;
  const folder = document.getElementById('import-folder').value.trim();
  if (!folder) { setImportStatus('Please enter the PDF folder path.', 'error'); return; }

  const btn = document.getElementById('btn-import');
  const btnText = document.getElementById('import-btn-text');
  btn.disabled = true; importRunning = true;
  btnText.innerHTML = '<div class="spinner" style="border-top-color:#000"></div> Importing...';
  setImportStatus('Processing PDFs... please wait, this may take a while.', 'info');

  // Clear log
  const log = document.getElementById('import-log');
  log.innerHTML = ''; log.style.display = 'flex';
  document.getElementById('import-stats').style.display = 'none';
  logRow('info', '📁', 'Folder: ' + folder);
  logRow('info', '⏳', 'Connecting to MongoDB and reading PDFs...');

  try {
    const resp = await fetch('/import_folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder: folder })
    });

    const data = await resp.json();

    if (!resp.ok || data.error) {
      setImportStatus('Error: ' + (data.error || 'Unknown error'), 'error');
      logRow('error', '✖', data.error || 'Request failed');
      return;
    }

    // Show per-file results
    (data.file_results || []).forEach(fr => {
      if (fr.status === 'error') {
        logRow('error', '✖', '[' + fr.index + '] ' + fr.file + ' — ' + (fr.stage||'').toUpperCase() + ': ' + (fr.msg||'error'));
      } else {
        logRow('success', '✔',
          '[' + fr.index + '] ' + fr.file +
          ' → Ch.' + (fr.chapter||'?') +
          '  extracted:' + fr.count +
          '  inserted:' + fr.inserted +
          '  updated:' + fr.modified +
          (fr.errors > 0 ? '  errors:' + fr.errors : ''));
      }
    });

    // Error details
    if (data.error_details && data.error_details.length) {
      logRow('warn', '⚠', '--- Error Details ---');
      data.error_details.forEach(e => {
        logRow('error', '✖', '[' + (e.stage||'?').toUpperCase() + '] ' + e.file + (e.hs_code?' hs='+e.hs_code:'') + ': ' + e.error);
      });
    }

    // Summary stats
    document.getElementById('imp-ins').textContent = data.inserted;
    document.getElementById('imp-mod').textContent = data.modified;
    document.getElementById('imp-err').textContent = data.errors;
    document.getElementById('import-stats').style.display = 'grid';

    const skippedMsg = data.skipped > 0 ? '  |  Skipped: ' + data.skipped + ' PDFs' : '';
    logRow('success', '🎉',
      'DONE — ' + data.inserted + ' inserted, ' + data.modified + ' updated, ' +
      data.errors + ' doc errors' + skippedMsg);

    const ok = data.errors === 0 && data.skipped === 0;
    setImportStatus(
      ok ? '✅ All ' + data.total_files + ' PDFs imported into wizard.hscodes!'
         : '⚠ Import finished with issues — check log above.',
      ok ? 'success' : 'error'
    );

  } catch (e) {
    setImportStatus('Error: ' + e.message, 'error');
    logRow('error', '✖', 'Error: ' + e.message);
  } finally {
    btn.disabled = false; importRunning = false;
    btnText.innerHTML = '&#x1F680; Start Bulk Import';
  }
}

// ── Single PDF → MongoDB upload ───────────────────────────────────────────────
async function doUpload() {
  if (uploadRunning) return;
  const file = selectedUploadFile || (_ufi.files && _ufi.files[0]);
  if (!file) { _setUploadStatus('Please select a PDF file first.', 'error'); return; }

  const btn     = document.getElementById('btn-upload');
  const btnText = document.getElementById('upload-btn-text');
  btn.disabled = true; uploadRunning = true;
  btnText.innerHTML = '<div class="spinner"></div> Uploading...';
  _setUploadStatus('Extracting HS codes and uploading to MongoDB...', 'info');

  const log = document.getElementById('upload-log');
  log.innerHTML = ''; log.style.display = 'flex';
  document.getElementById('upload-stats').style.display = 'none';
  _logUpload('info', '&#x1F4C4;', 'File: ' + file.name);
  _logUpload('info', '&#x23F3;',  'Connecting to MongoDB and extracting HS codes...');

  const fd = new FormData();
  fd.append('pdf', file);

  try {
    const resp = await fetch('/upload_single', { method: 'POST', body: fd });
    const data = await resp.json();

    if (!resp.ok || data.error) {
      _setUploadStatus('Error: ' + (data.error || 'Unknown error'), 'error');
      _logUpload('error', '&#x2716;', data.error || 'Request failed');
      return;
    }

    _logUpload('success', '&#x2714;',
      'Chapter ' + (data.chapter || '?') +
      '  |  extracted: ' + data.extracted +
      '  |  inserted: '  + data.inserted +
      '  |  updated: '   + data.modified +
      (data.errors > 0 ? '  |  errors: ' + data.errors : ''));

    if (data.error_details && data.error_details.length) {
      _logUpload('warn', '&#x26A0;', '--- Error Details ---');
      data.error_details.forEach(e => _logUpload('error', '&#x2716;', e));
    }

    document.getElementById('upload-ins').textContent = data.inserted;
    document.getElementById('upload-mod').textContent = data.modified;
    document.getElementById('upload-err').textContent = data.errors;
    document.getElementById('upload-stats').style.display = 'grid';

    _logUpload('success', '&#x1F389;',
      'DONE — ' + data.inserted + ' new, ' + data.modified + ' updated. All other chapters untouched.');

    const ok = data.errors === 0;
    _setUploadStatus(
      ok ? '\u2705 Chapter ' + (data.chapter||'?') + ' upserted into wizard.hscodes!'
         : '\u26A0 Upload finished with ' + data.errors + ' errors \u2014 see log above.',
      ok ? 'success' : 'error'
    );
  } catch (e) {
    _setUploadStatus('Error: ' + e.message, 'error');
    _logUpload('error', '&#x2716;', 'Error: ' + e.message);
  } finally {
    btn.disabled = false; uploadRunning = false;
    btnText.innerHTML = '&#x2B06;&#xFE0F; Upload to MongoDB';
  }
}
</script>
</body>
</html>"""


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/extract', methods=['POST'])
def do_extract():
    if 'pdf' not in request.files:
        return jsonify({'error': 'No PDF file uploaded'}), 400

    f = request.files['pdf']
    if not f.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'File must be a PDF'}), 400

    chapter_override = request.form.get('chapter', '').strip()
    fileref_override = request.form.get('fileref', '').strip()

    # Save to temp file
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    try:
        f.save(tmp.name)
        tmp.close()

        result = extract(tmp.name)

        # Apply overrides
        if fileref_override:
            result['file_reference'] = fileref_override
        if chapter_override:
            result['chapter'] = chapter_override.zfill(2)

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


# ── MongoDB helpers ──────────────────────────────────────────────────────────

def get_mongo_col():
    client = MongoClient(MONGO_URI, server_api=ServerApi('1'), serverSelectionTimeoutMS=15_000)
    client.admin.command('ping')
    col = client[DB_NAME][COL_NAME]
    col.create_index("chapter")
    col.create_index("heading")
    col.create_index([("hs_code", 1)], unique=True)
    return col


def build_doc(item: dict, chapter_info: dict, source_file: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
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


def upsert_docs(col, docs):
    """Bulk upsert; returns (inserted, modified, errors[])."""
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


# ── Import route (plain JSON – no streaming) ─────────────────────────────────

@app.route('/import_folder', methods=['POST'])
def import_folder():
    """Process all PDFs in a folder and return a single JSON result."""
    if not MONGO_AVAILABLE:
        return jsonify({'error': 'pymongo not installed'}), 500

    data       = request.get_json(force=True) or {}
    pdf_folder = data.get('folder', '').strip()

    if not pdf_folder or not os.path.isdir(pdf_folder):
        return jsonify({'error': f'Folder not found: {pdf_folder}'}), 400

    pdf_files = sorted(glob.glob(os.path.join(pdf_folder, '*.pdf')))
    if not pdf_files:
        return jsonify({'error': 'No PDF files found in folder'}), 400

    # Connect to MongoDB
    try:
        col = get_mongo_col()
    except Exception as e:
        return jsonify({'error': f'MongoDB connection failed: {e}'}), 500

    total_ins = total_mod = total_err = total_skip = 0
    all_errors = []
    file_results = []

    for idx, pdf_path in enumerate(pdf_files, 1):
        fname = os.path.basename(pdf_path)
        file_result = {'file': fname, 'index': idx, 'status': 'ok',
                       'chapter': '', 'count': 0, 'inserted': 0, 'modified': 0, 'errors': 0}

        # Extract
        try:
            result  = extract(pdf_path)
            items   = result.get('items', [])
            chap_no = result.get('chapter', '??')
            if not items:
                raise ValueError('No HS code items found in PDF')
        except Exception as e:
            msg = str(e)
            file_result.update({'status': 'error', 'stage': 'extract', 'msg': msg})
            all_errors.append({'file': fname, 'stage': 'extract', 'error': msg})
            total_skip += 1
            file_results.append(file_result)
            continue

        chapter_info = {
            'chapter'            : result.get('chapter', ''),
            'chapter_description': result.get('chapter_description', ''),
            'chapter_exceptions' : result.get('chapter_exceptions', []),
        }
        file_result['chapter'] = chap_no
        file_result['count']   = len(items)

        # Build documents
        docs = []
        for item in items:
            try:
                docs.append(build_doc(item, chapter_info, fname))
            except Exception as e:
                all_errors.append({'file': fname, 'hs_code': item.get('hs_code','?'),
                                   'stage': 'build', 'error': str(e)})

        # Upsert to MongoDB
        try:
            ins, mod, errs = upsert_docs(col, docs)
            total_ins += ins
            total_mod += mod
            total_err += len(errs)
            file_result.update({'inserted': ins, 'modified': mod, 'errors': len(errs)})
            for err_msg in errs:
                all_errors.append({'file': fname, 'stage': 'upload', 'error': err_msg})
        except Exception as e:
            msg = str(e)
            file_result.update({'status': 'error', 'stage': 'upload', 'msg': msg})
            all_errors.append({'file': fname, 'stage': 'upload', 'error': msg})
            total_skip += 1

        file_results.append(file_result)

    return jsonify({
        'ok'           : True,
        'total_files'  : len(pdf_files),
        'skipped'      : total_skip,
        'inserted'     : total_ins,
        'modified'     : total_mod,
        'errors'       : total_err,
        'file_results' : file_results,
        'error_details': all_errors,
    })


# ── Single PDF Upload route ──────────────────────────────────────────────────

@app.route('/upload_single', methods=['POST'])
def upload_single():
    """
    Upload one PDF, extract its HS codes, and upsert into MongoDB.
    Uses UpdateOne(upsert=True) keyed on hs_code, so every other chapter
    already in the DB is completely untouched.
    """
    if not MONGO_AVAILABLE:
        return jsonify({'error': 'pymongo not installed'}), 500

    if 'pdf' not in request.files:
        return jsonify({'error': 'No PDF file uploaded'}), 400

    f = request.files['pdf']
    if not f.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'File must be a PDF'}), 400

    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    try:
        f.save(tmp.name)
        tmp.close()

        # ── Extract ───────────────────────────────────────────────────────────
        try:
            result = extract(tmp.name)
        except Exception as e:
            traceback.print_exc()
            return jsonify({'error': f'Extraction failed: {e}'}), 500

        items = result.get('items', [])
        if not items:
            return jsonify({'error': 'No HS code items found in this PDF'}), 400

        chapter_info = {
            'chapter'            : result.get('chapter', ''),
            'chapter_description': result.get('chapter_description', ''),
            'chapter_exceptions' : result.get('chapter_exceptions', []),
        }

        # ── Build documents ───────────────────────────────────────────────────
        docs         = []
        build_errors = []
        for item in items:
            try:
                docs.append(build_doc(item, chapter_info, f.filename))
            except Exception as e:
                build_errors.append(f"Build error hs={item.get('hs_code','?')}: {e}")

        # ── Connect & upsert ──────────────────────────────────────────────────
        try:
            col = get_mongo_col()
        except Exception as e:
            return jsonify({'error': f'MongoDB connection failed: {e}'}), 500

        ins, mod, errs = upsert_docs(col, docs)

        return jsonify({
            'ok'          : True,
            'chapter'     : result.get('chapter', ''),
            'extracted'   : len(items),
            'inserted'    : ins,
            'modified'    : mod,
            'errors'      : len(errs) + len(build_errors),
            'error_details': errs + build_errors,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"\n[OK] HS Code Extractor running at http://0.0.0.0:{port}\n")
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)
