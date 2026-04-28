"""Kanıt toplama - screenshot, DOM dump, HAR capture."""

import json
import logging
import os
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

# Gizli LINK'leri tespit et + sayfanın üstüne BANNER ekle (sayfa yapısını BOZMA)
# Eski yaklaşım her hidden element'i görünür yapıyordu → site iskeleti bozuluyor.
# Yeni yaklaşım: sadece <a> anchor'ları analiz et, banner ile özetle.
REVEAL_HIDDEN_JS = r"""() => {
    const hidden = [];
    const seen = new Set();
    // Site'nin kendi domain'ini bul (same-domain filter için)
    const siteHost = (location.hostname || '').replace(/^www\./, '').toLowerCase();
    const isInternal = (url) => {
        try {
            const h = new URL(url, location.href).hostname.toLowerCase().replace(/^www\./, '');
            return h === siteHost || h.endsWith('.' + siteHost) || siteHost.endsWith('.' + h);
        } catch { return false; }
    };
    document.querySelectorAll('a[href]').forEach(a => {
        const href = a.href || '';
        if (!href || seen.has(href)) return;
        // Site'nin kendi link'leri = nav/menu/dropdown — banner'a ATLA
        if (isInternal(href)) return;
        const s = window.getComputedStyle(a);
        const rect = a.getBoundingClientRect();
        const cssHidden = (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0);
        const offscreen = (rect.left < -1000 || rect.top < -1000);
        const zeroSize = (rect.width === 0 || rect.height === 0);
        // parent zinciri kontrol
        let parentHidden = false;
        let parentReason = '';
        let p = a.parentElement;
        let depth = 0;
        while (p && p !== document.body && depth < 10) {
            const ps = window.getComputedStyle(p);
            const pr = p.getBoundingClientRect();
            if (ps.display === 'none') { parentHidden = true; parentReason = 'parent display:none'; break; }
            if (ps.visibility === 'hidden') { parentHidden = true; parentReason = 'parent visibility:hidden'; break; }
            if (parseFloat(ps.opacity) === 0) { parentHidden = true; parentReason = 'parent opacity:0'; break; }
            if (parseInt(ps.height) === 0 && (ps.overflow === 'hidden' || ps.overflow === 'clip')) { parentHidden = true; parentReason = 'parent height:0;overflow:hidden'; break; }
            if (ps.position === 'absolute' && parseInt(ps.left) < -1000) { parentHidden = true; parentReason = 'parent off-screen'; break; }
            p = p.parentElement; depth++;
        }
        if (cssHidden || offscreen || zeroSize || parentHidden) {
            seen.add(href);
            const reasons = [];
            if (cssHidden) reasons.push(s.display === 'none' ? 'display:none' : s.visibility === 'hidden' ? 'visibility:hidden' : 'opacity:0');
            if (offscreen) reasons.push('off-screen');
            if (zeroSize) reasons.push('0×0 size');
            if (parentHidden) reasons.push(parentReason);
            hidden.push({
                href: href,
                text: (a.textContent || '').trim().slice(0, 80),
                title: (a.getAttribute('title') || '').trim().slice(0, 80),
                reasons: reasons.join(', ')
            });
        }
    });
    if (hidden.length === 0) return 0;

    // Banner: sayfanın en üstüne kırmızı kanıt kutusu (sayfa yapısını bozmadan)
    const banner = document.createElement('div');
    banner.style.cssText = 'all:initial;display:block;background:#7a0000;color:white;padding:24px 28px;font-family:Inter,Arial,sans-serif;font-size:14px;border:6px solid #ff0033;margin:0 0 24px 0;position:relative;z-index:2147483647;line-height:1.5';
    const title = document.createElement('h2');
    title.style.cssText = 'all:initial;color:white;font-family:Bitter,Georgia,serif;font-size:26px;font-weight:700;margin:0 0 8px 0;display:block';
    title.textContent = '⚠ ' + hidden.length + ' HIDDEN LINKS — INJECTED ON THIS PAGE';
    banner.appendChild(title);
    const sub = document.createElement('p');
    sub.style.cssText = 'all:initial;color:#ffd1d1;font-family:Inter,Arial,sans-serif;font-size:13px;margin:0 0 14px 0;display:block';
    sub.textContent = 'These anchors are hidden from regular visitors but counted by search engines for ranking laundering. Captured by AbuseRadar.';
    banner.appendChild(sub);
    const list = document.createElement('ol');
    list.style.cssText = 'all:initial;display:block;background:#3a0000;padding:14px 18px 14px 38px;margin:0;font-family:JetBrains Mono,Consolas,monospace;font-size:12px;color:white;list-style:decimal';
    hidden.slice(0, 50).forEach(h => {
        const li = document.createElement('li');
        li.style.cssText = 'all:initial;display:list-item;color:white;margin:6px 0;font-family:JetBrains Mono,Consolas,monospace;font-size:12px;line-height:1.5';
        const anchorText = document.createElement('strong');
        anchorText.style.cssText = 'all:initial;color:#ffe066;font-weight:700;font-family:JetBrains Mono,Consolas,monospace;font-size:13px';
        anchorText.textContent = h.text || '(no text)';
        const arrow = document.createElement('span');
        arrow.style.cssText = 'all:initial;color:#ffaaaa;margin:0 8px';
        arrow.textContent = '→';
        const url = document.createElement('code');
        url.style.cssText = 'all:initial;color:#7fdbff;font-family:JetBrains Mono,Consolas,monospace;font-size:12px';
        url.textContent = h.href;
        li.appendChild(anchorText);
        li.appendChild(arrow);
        li.appendChild(url);
        if (h.title && h.title !== h.text) {
            const titleSpan = document.createElement('em');
            titleSpan.style.cssText = 'all:initial;color:#cccccc;margin-left:8px;font-style:italic;font-family:JetBrains Mono,Consolas,monospace;font-size:11px';
            titleSpan.textContent = '(title: "' + h.title + '")';
            li.appendChild(titleSpan);
        }
        const reasonsSpan = document.createElement('span');
        reasonsSpan.style.cssText = 'all:initial;color:#aaaaaa;display:block;font-family:Inter,Arial,sans-serif;font-size:10px;margin-top:2px;font-style:italic';
        reasonsSpan.textContent = '   hiding: ' + h.reasons;
        li.appendChild(reasonsSpan);
        list.appendChild(li);
    });
    if (hidden.length > 50) {
        const more = document.createElement('li');
        more.style.cssText = 'all:initial;display:list-item;color:#ffaaaa;margin:8px 0;font-style:italic;font-family:Inter,Arial,sans-serif';
        more.textContent = '… and ' + (hidden.length - 50) + ' more (full list in evidence bundle)';
        list.appendChild(more);
    }
    banner.appendChild(list);
    document.body.insertBefore(banner, document.body.firstChild);
    // Sayfanın en üstüne scroll et
    window.scrollTo(0, 0);
    return hidden.length;
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
