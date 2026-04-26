#!/usr/bin/env python3
"""Gemini Nano Banana image generator. Usage: gen.py <out.png> <aspect> <prompt>"""
import sys, os, json, base64, urllib.request, pathlib

key_line = next(l for l in pathlib.Path('/Users/muratkara/Report/seospamwatch/.env').read_text().splitlines() if l.startswith('GEMINI_API_KEY='))
KEY = key_line.split('=', 1)[1].strip()

out, ar, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
body = {
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {"imageConfig": {"aspectRatio": ar}}
}
req = urllib.request.Request(
    url,
    data=json.dumps(body).encode(),
    headers={"x-goog-api-key": KEY, "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as r:
    d = json.loads(r.read())

if 'error' in d:
    print("ERROR:", json.dumps(d['error'], indent=2)); sys.exit(1)

parts = d.get('candidates', [{}])[0].get('content', {}).get('parts', [])
for p in parts:
    inline = p.get('inlineData') or p.get('inline_data')
    if inline:
        pathlib.Path(out).write_bytes(base64.b64decode(inline['data']))
        print(f"OK -> {out} ({pathlib.Path(out).stat().st_size} bytes)")
        sys.exit(0)
print("NO IMAGE in response:", json.dumps(d)[:500]); sys.exit(2)
