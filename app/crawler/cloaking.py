"""Cloaking tespiti - 3 farklı User-Agent ile aynı URL'yi karşılaştır."""

import asyncio
import logging
import re
from dataclasses import dataclass, field

import httpx
from playwright.async_api import async_playwright

from config import settings

logger = logging.getLogger(__name__)

USER_AGENTS = {
    "normal": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "googlebot": (
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    ),
    "googlebot_mobile": (
        "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36 "
        "(compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    ),
}

GAMBLING_KEYWORDS = [
    "deneme bonusu", "bahis", "casino", "slot ", "betting",
    "grandpashabet", "sahabet", "onwin", "jojobet",
    "สล็อต", "บาคาร่า", "토토", "먹튀",
]


@dataclass
class CloakingResult:
    url: str
    is_cloaking: bool = False
    evidence: list[str] = field(default_factory=list)
    screenshots: dict[str, str] = field(default_factory=dict)
    responses: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "is_cloaking": self.is_cloaking,
            "evidence": self.evidence,
            "screenshots": self.screenshots,
            "response_summary": {
                k: {
                    "status": v.get("status_code"),
                    "title": v.get("title"),
                    "link_count": v.get("link_count"),
                    "gambling_kw": v.get("gambling_keywords"),
                    "body_length": v.get("body_length"),
                }
                for k, v in self.responses.items()
            },
        }


def _count_gambling(text: str) -> int:
    text_lower = text.lower()
    return sum(1 for kw in GAMBLING_KEYWORDS if kw in text_lower)


async def detect_cloaking(url: str, domain: str, evidence_dir: str | None = None) -> CloakingResult:
    """Aynı URL'yi 3 farklı UA ile çekip cloaking tespit et."""
    result = CloakingResult(url=url)
    logger.info(f"[{domain}] Cloaking testi başlıyor")

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)

            for ua_name, ua_string in USER_AGENTS.items():
                try:
                    page = await browser.new_page(
                        user_agent=ua_string,
                        viewport={"width": 1920, "height": 1080},
                    )
                    resp = await page.goto(
                        url, wait_until="networkidle",
                        timeout=settings.crawl_page_timeout,
                    )
                    await asyncio.sleep(2)

                    title = await page.title()
                    body_text = await page.evaluate("() => document.body?.innerText || ''")
                    link_count = await page.evaluate(
                        "() => document.querySelectorAll('a[href]').length"
                    )
                    final_url = page.url

                    html = await page.content()
                    response_data = {
                        "status_code": resp.status if resp else 0,
                        "final_url": final_url,
                        "title": title,
                        "body_length": len(body_text),
                        "link_count": link_count,
                        "gambling_keywords": _count_gambling(body_text),
                        "html": html,  # full HTML for hacklink extraction
                    }
                    result.responses[ua_name] = response_data

                    # Screenshot kaydet
                    if evidence_dir:
                        from pathlib import Path
                        ss_dir = Path(evidence_dir) / "screenshots"
                        ss_dir.mkdir(parents=True, exist_ok=True)
                        ss_path = str(ss_dir / f"cloaking-{ua_name}.png")
                        await page.screenshot(path=ss_path, full_page=True, timeout=15000)
                        result.screenshots[ua_name] = ss_path

                    await page.close()

                except Exception as e:
                    logger.warning(f"[{domain}] {ua_name} UA hatası: {e}")
                    result.responses[ua_name] = {"error": str(e)}

            await browser.close()

    except Exception as e:
        logger.error(f"[{domain}] Cloaking testi hatası: {e}")
        return result

    # ═══ KARŞILAŞTIRMA ═══
    normal = result.responses.get("normal", {})
    bot = result.responses.get("googlebot", {})

    if "error" in normal or "error" in bot:
        return result

    # 1. Status code farkı
    if normal.get("status_code") != bot.get("status_code"):
        result.is_cloaking = True
        result.evidence.append(
            f"Status farkı: user={normal['status_code']}, bot={bot['status_code']}"
        )

    # 2. Redirect farkı
    if normal.get("final_url") != bot.get("final_url"):
        result.is_cloaking = True
        result.evidence.append(
            f"Redirect farkı: user→{normal['final_url']}, bot→{bot['final_url']}"
        )

    # 3. Title farkı
    n_title = (normal.get("title") or "").strip().lower()
    b_title = (bot.get("title") or "").strip().lower()
    if n_title and b_title and n_title != b_title:
        result.is_cloaking = True
        result.evidence.append(f"Title farkı: user='{n_title}', bot='{b_title}'")

    # 4. İçerik boyutu %30+ fark
    n_len = normal.get("body_length", 0)
    b_len = bot.get("body_length", 0)
    avg = (n_len + b_len) / 2
    if avg > 0 and abs(n_len - b_len) / avg > 0.3:
        result.is_cloaking = True
        pct = int(abs(n_len - b_len) / avg * 100)
        result.evidence.append(f"İçerik boyutu farkı: user={n_len}, bot={b_len} (%{pct})")

    # 5. Gambling keyword farkı
    n_gk = normal.get("gambling_keywords", 0)
    b_gk = bot.get("gambling_keywords", 0)
    if b_gk > n_gk * 2 and b_gk > 3:
        result.is_cloaking = True
        result.evidence.append(f"Gambling keyword farkı: user={n_gk}, bot={b_gk}")

    # 6. Link sayısı ciddi fark
    n_links = normal.get("link_count", 0)
    b_links = bot.get("link_count", 0)
    if b_links > n_links * 1.5 and abs(b_links - n_links) > 20:
        result.is_cloaking = True
        result.evidence.append(f"Link sayısı farkı: user={n_links}, bot={b_links}")

    if result.is_cloaking:
        logger.warning(f"[{domain}] ⚠️ CLOAKING TESPİT EDİLDİ: {result.evidence}")
    else:
        logger.info(f"[{domain}] Cloaking yok")

    return result
