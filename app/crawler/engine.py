"""Ana crawl engine - site analizi orkestratörü."""

import asyncio
import logging
from datetime import datetime
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright

from config import settings
from models.database import DetectedHacklink, Site, async_session
from sqlalchemy import select

from .evidence import collect_evidence
from .hacklink_detector import EXTRACT_ALL_LINKS_JS, analyze_links
from .html_analyzer import (
    compare_raw_vs_rendered,
    extract_hacklinks_from_html,
    extract_injection_scripts,
)

logger = logging.getLogger(__name__)


async def get_known_spam_domains() -> set[str]:
    """DB'den bilinen spam/C2 domainlerini al."""
    async with async_session() as session:
        result = await session.execute(
            select(DetectedHacklink.target_domain).distinct()
        )
        hacklink_domains = {r[0] for r in result.all() if r[0]}

        from models.database import C2Domain
        result = await session.execute(select(C2Domain.domain))
        c2_domains = {r[0] for r in result.all() if r[0]}

    return hacklink_domains | c2_domains


async def crawl_and_analyze(url: str, domain: str | None = None) -> dict:
    """Tek bir siteyi crawl edip analiz et.

    3 katmanlı analiz:
    1. Raw HTTP → HTML gömülü enjeksiyon
    2. Playwright render → JS enjeksiyon + 6 kural hacklink
    3. Raw vs Rendered karşılaştırma
    """
    if not domain:
        domain = urlparse(url).hostname or ""

    logger.info(f"[{domain}] Crawl başlıyor: {url}")
    result = {
        "url": url,
        "domain": domain,
        "status": "pending",
        "raw_hacklinks": [],
        "rendered_hacklinks": [],
        "js_diff_hacklinks": [],
        "injection_scripts": [],
        "total_hacklinks": 0,
        "evidence_path": None,
        "error": None,
    }

    known_spam = await get_known_spam_domains()

    # ═══ KATMAN 1: Raw HTTP ═══
    raw_html = ""
    raw_link_set = set()
    try:
        async with httpx.AsyncClient(
            timeout=settings.crawl_page_timeout / 1000,
            follow_redirects=True,
            headers={"User-Agent": settings.crawl_user_agent},
        ) as client:
            resp = await client.get(url)
            raw_html = resp.text
            result["http_code"] = resp.status_code

        # HTML gömülü hacklink tespiti
        result["raw_hacklinks"] = extract_hacklinks_from_html(raw_html, domain)
        result["injection_scripts"] = extract_injection_scripts(raw_html)

        # Raw linkleri çıkar (karşılaştırma için)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw_html, "lxml")
        raw_link_set = {a["href"] for a in soup.find_all("a", href=True)}

        logger.info(
            f"[{domain}] Raw analiz: {len(result['raw_hacklinks'])} hacklink, "
            f"{len(result['injection_scripts'])} enjeksiyon script"
        )
    except Exception as e:
        logger.error(f"[{domain}] Raw HTTP hatası: {e}")
        result["error"] = f"raw_http: {e}"

    # ═══ KATMAN 2: Playwright Render ═══
    rendered_link_set = set()
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent=settings.crawl_user_agent,
                viewport={"width": 1920, "height": 1080},
            )

            await page.goto(url, wait_until="networkidle", timeout=settings.crawl_page_timeout)
            await asyncio.sleep(2)  # JS'lerin çalışması için ekstra bekleme

            # Tüm linkleri çıkar + 6 kural ile hacklink tespit
            all_links = await page.evaluate(EXTRACT_ALL_LINKS_JS)
            rendered_analysis = analyze_links(all_links, domain, known_spam)
            result["rendered_hacklinks"] = rendered_analysis["hacklinks"]

            # Rendered link set (karşılaştırma için)
            rendered_link_set = {link.get("href", "") for link in all_links}

            logger.info(
                f"[{domain}] Rendered analiz: {rendered_analysis['hacklink_count']} hacklink / "
                f"{rendered_analysis['total_links']} toplam link"
            )

            # ═══ KATMAN 3: Raw vs Rendered fark ═══
            if raw_link_set:
                result["js_diff_hacklinks"] = compare_raw_vs_rendered(
                    raw_link_set, rendered_link_set, domain
                )
                if result["js_diff_hacklinks"]:
                    logger.info(
                        f"[{domain}] JS diff: {len(result['js_diff_hacklinks'])} "
                        f"JS ile enjekte edilmiş link"
                    )

            # Toplam hacklink sayısı (deduplicate href'e göre)
            all_hacklink_hrefs = set()
            for hl in result["raw_hacklinks"] + result["rendered_hacklinks"] + result["js_diff_hacklinks"]:
                all_hacklink_hrefs.add(hl.get("href", ""))
            result["total_hacklinks"] = len(all_hacklink_hrefs)

            # Kanıt toplama
            combined_analysis = {
                "raw_hacklinks": result["raw_hacklinks"],
                "rendered_hacklinks": result["rendered_hacklinks"],
                "js_diff_hacklinks": result["js_diff_hacklinks"],
                "injection_scripts": result["injection_scripts"],
                "total_hacklinks": result["total_hacklinks"],
            }
            result["evidence_path"] = await collect_evidence(
                page, domain, raw_html, combined_analysis
            )

            await browser.close()

    except Exception as e:
        logger.error(f"[{domain}] Playwright hatası: {e}")
        result["error"] = f"playwright: {e}"

    result["status"] = "completed" if result["total_hacklinks"] > 0 else "clean"
    logger.info(
        f"[{domain}] Crawl tamamlandı: {result['total_hacklinks']} hacklink, "
        f"durum={result['status']}"
    )

    return result


async def save_crawl_results(crawl_result: dict):
    """Crawl sonuçlarını DB'ye kaydet."""
    async with async_session() as session:
        domain = crawl_result["domain"]

        # Site kaydını güncelle
        site_result = await session.execute(
            select(Site).where(Site.domain == domain)
        )
        site = site_result.scalar_one_or_none()
        if not site:
            site = Site(domain=domain, url=crawl_result["url"])
            session.add(site)
            await session.flush()

        site.last_crawled_at = datetime.utcnow()
        site.injection_verified = crawl_result["total_hacklinks"] > 0
        site.status = "infected" if site.injection_verified else "clean"

        # Hacklink'leri kaydet
        all_hacklinks = (
            crawl_result["raw_hacklinks"]
            + crawl_result["rendered_hacklinks"]
            + crawl_result["js_diff_hacklinks"]
        )
        seen_hrefs = set()
        for hl in all_hacklinks:
            href = hl.get("href", "")
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)

            hacklink = DetectedHacklink(
                site_id=site.id,
                href=href,
                anchor_text=hl.get("text", ""),
                target_domain=hl.get("target_domain", ""),
                detection_method=hl.get("method", hl.get("hiding_method", "unknown")),
                hiding_technique=hl.get("hiding_css", hl.get("hiding_method", "")),
                spam_score=hl.get("score", 0),
                detection_reasons=hl.get("reasons", []),
                found_in=hl.get("found_in", "unknown"),
                status="active",
            )
            session.add(hacklink)

        await session.commit()
        logger.info(f"[{domain}] DB'ye kaydedildi: {len(seen_hrefs)} hacklink")
