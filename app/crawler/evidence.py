"""Kanıt toplama - screenshot, DOM dump, HAR capture."""

import json
import logging
import os
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

# Gizli linkleri görünür yapan JS
REVEAL_HIDDEN_JS = """() => {
    let count = 0;
    document.querySelectorAll('*').forEach(el => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden' ||
            s.opacity === '0' || parseInt(s.left) < -9000) {
            el.style.setProperty('display', 'block', 'important');
            el.style.setProperty('visibility', 'visible', 'important');
            el.style.setProperty('opacity', '1', 'important');
            el.style.setProperty('position', 'static', 'important');
            el.style.setProperty('left', 'auto', 'important');
            el.style.setProperty('font-size', '14px', 'important');
            el.style.setProperty('background', 'rgba(255,0,0,0.2)', 'important');
            el.style.setProperty('border', '3px solid red', 'important');
            el.style.setProperty('padding', '5px', 'important');
            count++;
        }
    });
    document.querySelectorAll('[data-wpl]').forEach(el => {
        el.style.setProperty('background', 'rgba(255,0,0,0.7)', 'important');
        el.style.setProperty('color', 'white', 'important');
        el.style.setProperty('font-size', '16px', 'important');
        el.style.setProperty('display', 'block', 'important');
        el.style.setProperty('padding', '10px', 'important');
        el.style.setProperty('border', '3px solid yellow', 'important');
        count++;
    });
    return count;
}"""


async def collect_evidence(page, domain: str, raw_html: str, analysis: dict) -> str:
    """Bir site için tüm kanıtları topla.

    Returns:
        evidence_dir yolu
    """
    evidence_dir = Path(settings.evidence_path) / domain
    screenshots_dir = evidence_dir / "screenshots"
    dom_dir = evidence_dir / "dom"
    analysis_dir = evidence_dir / "analysis"

    for d in [screenshots_dir, dom_dir, analysis_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. Normal kullanıcı görünümü screenshot
    try:
        await page.screenshot(
            path=str(screenshots_dir / "user-view.png"),
            full_page=True,
            timeout=15000,
        )
        logger.info(f"[{domain}] User view screenshot alındı")
    except Exception as e:
        logger.warning(f"[{domain}] User screenshot hatası: {e}")

    # 2. Gizli linkleri görünür yap + screenshot
    try:
        revealed = await page.evaluate(REVEAL_HIDDEN_JS)
        if revealed > 0:
            await page.screenshot(
                path=str(screenshots_dir / "hidden-links-revealed.png"),
                full_page=True,
                timeout=15000,
            )
            logger.info(f"[{domain}] {revealed} gizli element açığa çıkarıldı")
    except Exception as e:
        logger.warning(f"[{domain}] Reveal screenshot hatası: {e}")

    # 3. Raw HTML kaydet
    try:
        with open(dom_dir / "raw.html", "w", encoding="utf-8") as f:
            f.write(raw_html)
    except Exception as e:
        logger.warning(f"[{domain}] Raw HTML kaydetme hatası: {e}")

    # 4. Rendered DOM kaydet
    try:
        rendered = await page.content()
        with open(dom_dir / "rendered.html", "w", encoding="utf-8") as f:
            f.write(rendered)
    except Exception as e:
        logger.warning(f"[{domain}] Rendered DOM kaydetme hatası: {e}")

    # 5. Analiz sonuçlarını kaydet
    try:
        with open(analysis_dir / "hacklinks.json", "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.warning(f"[{domain}] Analiz kaydetme hatası: {e}")

    logger.info(f"[{domain}] Kanıtlar kaydedildi: {evidence_dir}")
    return str(evidence_dir)
