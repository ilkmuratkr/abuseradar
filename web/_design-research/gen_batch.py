#!/usr/bin/env python3
"""Read prompts.json and generate all images in parallel-ish via threads."""
import json, base64, urllib.request, pathlib, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "img" / "generated"
OUT_DIR.mkdir(parents=True, exist_ok=True)

KEY = next(l.split('=', 1)[1].strip() for l in (ROOT.parent / ".env").read_text().splitlines() if l.startswith('GEMINI_API_KEY='))
URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"

def gen(item):
    out_path = OUT_DIR / item['out']
    body = {
        "contents": [{"parts": [{"text": item['prompt']}]}],
        "generationConfig": {"imageConfig": {"aspectRatio": item['ar']}}
    }
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode(),
        headers={"x-goog-api-key": KEY, "Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read())
    except Exception as e:
        return (item['out'], f"REQ-ERR: {e}")
    if 'error' in d:
        return (item['out'], f"API-ERR: {d['error'].get('message','?')}")
    parts = d.get('candidates', [{}])[0].get('content', {}).get('parts', [])
    for p in parts:
        inline = p.get('inlineData') or p.get('inline_data')
        if inline:
            out_path.write_bytes(base64.b64decode(inline['data']))
            return (item['out'], f"OK {out_path.stat().st_size}")
    return (item['out'], "NO-IMG")

prompts = json.loads((pathlib.Path(__file__).parent / "prompts.json").read_text())
print(f"Generating {len(prompts)} images in parallel...")
with ThreadPoolExecutor(max_workers=6) as ex:
    futures = [ex.submit(gen, p) for p in prompts]
    for f in as_completed(futures):
        name, status = f.result()
        print(f"  {name:30s} {status}")
print("Done.")
