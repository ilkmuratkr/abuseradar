"""Filesystem reader for evidence vault."""

import json
from pathlib import Path
from typing import Optional

from config import settings

EVIDENCE_ROOT = Path(settings.evidence_path)


def list_bundles() -> list[dict]:
    """Tüm evidence bundle'larını listele (her domain bir bundle)."""
    if not EVIDENCE_ROOT.exists():
        return []

    bundles = []
    for site_dir in sorted(EVIDENCE_ROOT.iterdir()):
        if not site_dir.is_dir():
            continue
        bundle = _bundle_summary(site_dir)
        bundles.append(bundle)

    bundles.sort(key=lambda b: b.get("captured_at") or "", reverse=True)
    return bundles


def get_bundle(domain: str) -> Optional[dict]:
    site_dir = EVIDENCE_ROOT / domain
    if not site_dir.is_dir():
        return None
    return _bundle_summary(site_dir, full=True)


def get_hacklinks(domain: str) -> Optional[dict]:
    """analysis/hacklinks.json içeriğini döner."""
    p = EVIDENCE_ROOT / domain / "analysis" / "hacklinks.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_screenshot_path(domain: str, index: int) -> Optional[Path]:
    """N. ekran görüntüsünün dosya yolu."""
    ss_dir = EVIDENCE_ROOT / domain / "screenshots"
    if not ss_dir.is_dir():
        return None
    pngs = sorted(ss_dir.glob("*.png"))
    if 0 <= index < len(pngs):
        return pngs[index]
    return None


def list_dom_files(domain: str) -> list[dict]:
    """DOM dump dosyalarını listele."""
    dom_dir = EVIDENCE_ROOT / domain / "dom"
    if not dom_dir.is_dir():
        return []
    out = []
    for f in sorted(dom_dir.glob("*.html")):
        out.append({"name": f.name, "size": f.stat().st_size})
    return out


def get_dom_content(domain: str, name: str, max_chars: int = 200_000) -> Optional[str]:
    """DOM dump içeriği (uzunsa kısalt)."""
    p = EVIDENCE_ROOT / domain / "dom" / name
    if not p.is_file() or ".." in name or "/" in name:
        return None
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[:max_chars]
    except Exception:
        return None


def _bundle_summary(site_dir: Path, full: bool = False) -> dict:
    """Bir site dizini için özet bilgi."""
    domain = site_dir.name
    ss_dir = site_dir / "screenshots"
    dom_dir = site_dir / "dom"
    analysis_file = site_dir / "analysis" / "hacklinks.json"

    screenshots = sorted(ss_dir.glob("*.png")) if ss_dir.is_dir() else []
    doms = sorted(dom_dir.glob("*.html")) if dom_dir.is_dir() else []

    captured_at = None
    if screenshots:
        captured_at = max(p.stat().st_mtime for p in screenshots)
    elif doms:
        captured_at = max(p.stat().st_mtime for p in doms)

    hacklink_count = 0
    c2_urls = []
    if analysis_file.is_file():
        try:
            data = json.loads(analysis_file.read_text(encoding="utf-8"))
            hacklink_count = len(data.get("rendered_hacklinks", [])) + len(
                data.get("js_diff_hacklinks", [])
            )
            for s in data.get("injection_scripts", []):
                c2_urls.extend(s.get("decoded_c2_urls", []))
        except Exception:
            pass

    bundle = {
        "domain": domain,
        "bundle_id": f"EV-{domain}",
        "captured_at": captured_at,
        "screenshots": len(screenshots),
        "dom_files": len(doms),
        "hacklink_count": hacklink_count,
        "has_analysis": analysis_file.is_file(),
        "c2_urls": list(set(c2_urls))[:5],
    }

    if full:
        bundle["screenshot_names"] = [p.name for p in screenshots]
        bundle["dom_names"] = [p.name for p in doms]
        # toplam boyut
        total = sum(
            p.stat().st_size for p in site_dir.rglob("*") if p.is_file()
        )
        bundle["size_bytes"] = total

    return bundle
