"""Test the /upload_single API endpoint."""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')

pdf_path = r'E:\bulk\New folder\Tariff 2022 Section IV Final_Chap_20.pdf'

print("Testing /upload_single endpoint...")
with open(pdf_path, 'rb') as f:
    r = requests.post(
        'http://localhost:5000/upload_single',
        files={'pdf': ('Chap_20.pdf', f, 'application/pdf')},
        timeout=120
    )

print(f"HTTP Status : {r.status_code}")
data = r.json()
print(f"OK          : {data.get('ok')}")
print(f"Chapter     : {data.get('chapter')}")
print(f"Extracted   : {data.get('extracted')}")
print(f"Inserted    : {data.get('inserted')}")
print(f"Updated     : {data.get('modified')}")
print(f"Errors      : {data.get('errors')}")
if data.get('error'):
    print(f"ERROR       : {data['error']}")
