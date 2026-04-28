"""Ana crawl engine - site analizi orkestratörü."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

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

MAX_PAGES_PER_SITE = 5  # multi-page crawl limit
SAME_DOMAIN_DELAY_SEC = 2  # sayfalar arası bekleme


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


async def crawl_with_fallback(url: str, domain: str | None = None) -> dict:
    """Crawl with multi-VPN fallback: VPN-TR → VPN-US → host network direct.

    İlk denemede TR (default crawl trafiği TR'den çıksın). Block/timeout/connection
    hatası olursa US'e fallback. Yine olmazsa host network (proxy yok). Crawler'da
    AI/Gemini çağrısı yok, host fallback bilgi sızdırmaz.
    """
    proxy_chain = [
        ("vpn-tr", "socks5h://vpn-tr:1080"),
        ("vpn-us", "socks5h://vpn-us:1080"),
        ("host", None),
    ]
    last_result = None
    for label, proxy in proxy_chain:
        logger.info(f"Crawl attempt via {label}: {url}")
        r = await crawl_and_analyze(url, domain=domain, proxy=proxy)
        r["egress"] = label
        # Başarılı: en az HTTP code geldi VEYA evidence toplandı
        if r.get("http_code") or r.get("total_hacklinks", 0) > 0 or r.get("evidence_path"):
            return r
        last_result = r
        logger.warning(f"[{label}] Crawl bilgi alınamadı, fallback denenecek. err={r.get('error')}")
    return last_result or {"status": "error", "error": "all_egresses_failed"}


async def crawl_and_analyze(
    url: str,
    domain: str | None = None,
    proxy: str | None = "socks5h://vpn-tr:1080",
) -> dict:
    """Tek bir siteyi crawl edip analiz et.

    3 katmanlı analiz:
    1. Raw HTTP → HTML gömülü enjeksiyon
    2. Playwright render → JS enjeksiyon + 6 kural hacklink
    3. Raw vs Rendered karşılaştırma

    `proxy`: SOCKS5 URL veya None (host network).
    """
    if not domain:
        domain = urlparse(url).hostname or ""

    logger.info(f"[{domain}] Crawl başlıyor: {url} (proxy={proxy})")
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
        "_proxy": proxy,
    }

    known_spam = await get_known_spam_domains()

    # ═══ KATMAN 1: Raw HTTP ═══
    raw_html = ""
    raw_link_set = set()
    proxy = result.get("_proxy")
    trust_env = proxy is None  # explicit None → host network direct
    try:
        client_kwargs = {
            "timeout": settings.crawl_page_timeout / 1000,
            "follow_redirects": True,
            "headers": {"User-Agent": settings.crawl_user_agent},
            "trust_env": trust_env,
        }
        if proxy:
            client_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**client_kwargs) as client:
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
            launch_opts = {"headless": True}
            if proxy:
                # SOCKS proxy URL → Playwright proxy format
                # socks5h://vpn-tr:1080  →  socks5://vpn-tr:1080
                pw_proxy = proxy.replace("socks5h://", "socks5://")
                launch_opts["proxy"] = {"server": pw_proxy}
            browser = await pw.chromium.launch(**launch_opts)
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

    # ═══ KATMAN 4: Cloaking probe (Googlebot UA pass) ═══
    # Aynı URL'yi 3 farklı UA ile çekip içerik farklarına bak.
    # Cloaking varsa hacklink çıkaramamış olsak bile **bu site compromise**.
    result["cloaking_detected"] = False
    result["cloaking_evidence"] = []
    try:
        from .cloaking import detect_cloaking

        cloak = await detect_cloaking(url, domain, evidence_dir=result.get("evidence_path"))
        result["cloaking_detected"] = cloak.is_cloaking
        result["cloaking_evidence"] = cloak.evidence

        # Googlebot UA'nın gördüğü HTML'den hacklink çıkar (varsa)
        bot_resp = cloak.responses.get("googlebot", {}) or {}
        bot_html = bot_resp.get("html", "")
        if bot_html:
            bot_hacklinks = extract_hacklinks_from_html(bot_html, domain)
            existing_hrefs = {hl.get("href") for hl in result["raw_hacklinks"] + result["rendered_hacklinks"] + result["js_diff_hacklinks"]}
            for hl in bot_hacklinks:
                href = hl.get("href")
                if href and href not in existing_hrefs:
                    hl["source"] = "cloaking_googlebot"
                    result["raw_hacklinks"].append(hl)
                    existing_hrefs.add(href)
            # Total güncelle
            all_hrefs = set()
            for hl in result["raw_hacklinks"] + result["rendered_hacklinks"] + result["js_diff_hacklinks"]:
                all_hrefs.add(hl.get("href", ""))
            result["total_hacklinks"] = len(all_hrefs)

        if cloak.is_cloaking:
            logger.warning(
                f"[{domain}] ⚠️ Cloaking sinyal: {len(cloak.evidence)} kanıt — "
                f"site Googlebot'a farklı içerik gösteriyor"
            )
    except Exception as e:
        logger.warning(f"[{domain}] Cloaking probe hatası: {e}")

    # ═══ TOTAL HACKLINK (Playwright fail olsa bile yeniden hesapla) ═══
    # Önemli: bu hesap Playwright try bloğunun İÇİNDE de var ama timeout
    # alınca atlanıyordu. Burada her zaman, son halinde tekrar hesaplanır.
    all_hrefs = set()
    for hl in (
        result.get("raw_hacklinks", [])
        + result.get("rendered_hacklinks", [])
        + result.get("js_diff_hacklinks", [])
    ):
        href = hl.get("href", "")
        if href:
            all_hrefs.add(href)
    result["total_hacklinks"] = len(all_hrefs)

    # ═══ STATUS LOGIC ═══
    if result["total_hacklinks"] > 0:
        result["status"] = "compromised"
    elif result["cloaking_detected"]:
        # Hidden link çıkaramadık ama Googlebot'a farklı sayfa = injection
        result["status"] = "cloaking_detected"
    elif result.get("http_code") and result["http_code"] < 400:
        # Erişildi, hiçbir şey bulunmadı = gerçek temiz
        result["status"] = "clean"
    else:
        # Hiç erişilemedi (timeout, block, DNS) — temiz değil, bilinmiyor
        result["status"] = "unreachable"
    logger.info(
        f"[{domain}] Crawl tamamlandı: {result['total_hacklinks']} hacklink, "
        f"durum={result['status']}"
    )

    return result


# ═══════════════════════════════════════════════════════════════════
# MULTI-PAGE CRAWL — page discovery + aggregate
# ═══════════════════════════════════════════════════════════════════


def _is_same_site(href: str, domain: str) -> bool:
    """URL site'nin kendi domain'inde mi? (alt-domain dahil)"""
    try:
        h = (urlparse(href).hostname or "").lower().replace("www.", "")
        d = (domain or "").lower().replace("www.", "")
        return h == d or h.endswith("." + d) or d.endswith("." + h)
    except Exception:
        return False


async def discover_pages(homepage_url: str, domain: str, max_pages: int = MAX_PAGES_PER_SITE) -> list[str]:
    """Homepage'den internal link'ler + sitemap.xml — max_pages'e kadar URL listesi."""
    pages = [homepage_url]
    seen = {homepage_url.rstrip("/")}

    # 1. Homepage'den internal link'ler
    try:
        async with httpx.AsyncClient(
            timeout=15.0, follow_redirects=True,
            headers={"User-Agent": settings.crawl_user_agent},
            proxy="socks5h://vpn-tr:1080", trust_env=False,
        ) as client:
            r = await client.get(homepage_url)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = urljoin(homepage_url, a["href"])
                # Internal mi?
                if not _is_same_site(href, domain):
                    continue
                # Fragment'i temizle, query bırak
                clean = href.split("#")[0].rstrip("/")
                if clean in seen or not clean.startswith("http"):
                    continue
                # PDF / image atla
                if any(clean.lower().endswith(x) for x in (".pdf", ".jpg", ".png", ".jpeg", ".gif", ".zip", ".doc", ".xls")):
                    continue
                pages.append(href)
                seen.add(clean)
                if len(pages) >= max_pages:
                    break
    except Exception as e:
        logger.warning(f"[{domain}] Internal link discovery hatası: {e}")

    # 2. sitemap.xml — daha fazla yer varsa doldur
    if len(pages) < max_pages:
        for sitemap_url in (f"https://{domain}/sitemap.xml", f"https://{domain}/sitemap_index.xml"):
            try:
                async with httpx.AsyncClient(
                    timeout=15.0, follow_redirects=True,
                    headers={"User-Agent": settings.crawl_user_agent},
                    proxy="socks5h://vpn-tr:1080", trust_env=False,
                ) as client:
                    r = await client.get(sitemap_url)
                    if r.status_code != 200:
                        continue
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(r.text, "xml")
                    for loc in soup.find_all("loc"):
                        url = loc.get_text().strip()
                        clean = url.split("#")[0].rstrip("/")
                        if clean in seen or not _is_same_site(url, domain):
                            continue
                        if any(clean.lower().endswith(x) for x in (".pdf", ".jpg", ".png", ".jpeg", ".gif", ".zip")):
                            continue
                        pages.append(url)
                        seen.add(clean)
                        if len(pages) >= max_pages:
                            break
                if len(pages) >= max_pages:
                    break
            except Exception:
                pass

    logger.info(f"[{domain}] Discovered {len(pages)} pages (homepage + internal + sitemap)")
    return pages[:max_pages]


async def crawl_site(homepage_url: str, max_pages: int = MAX_PAGES_PER_SITE) -> dict:
    """Multi-page crawl: anasayfa + internal links + sitemap (max N sayfa).

    Her sayfayı crawl_with_fallback ile çek, sonuçları aggregate et:
    - Unique injection scripts (hangi script hangi sayfada yüklü)
    - Hacklinks per source script
    - Total unique hacklinks
    - Cloaking signal (en az bir sayfada varsa)
    """
    domain = urlparse(homepage_url).hostname or ""
    pages = await discover_pages(homepage_url, domain, max_pages)

    aggregate = {
        "url": homepage_url,
        "domain": domain,
        "pages_crawled": 0,
        "pages_attempted": len(pages),
        "page_results": [],          # [{url, raw_count, js_count, http_code, scripts, status}]
        "unique_scripts": {},        # {src: {src, decoded_c2_urls, pages: [url1,...]}}
        "raw_hacklinks": [],
        "js_diff_hacklinks": [],
        "rendered_hacklinks": [],
        "injection_scripts": [],
        "total_hacklinks": 0,
        "cloaking_detected": False,
        "cloaking_evidence": [],
        "evidence_path": None,
        "status": "pending",
        "http_code": None,
        "egress": None,
    }

    seen_raw = set()
    seen_js = set()
    seen_rendered = set()

    for idx, page_url in enumerate(pages, start=1):
        # Same-domain rate limit — sayfalar arası bekle (ilk sayfa hariç)
        if idx > 1:
            logger.info(f"[{domain}] Page {idx}/{len(pages)}: waiting {SAME_DOMAIN_DELAY_SEC}s (rate-limit) → {page_url}")
            await asyncio.sleep(SAME_DOMAIN_DELAY_SEC)
        else:
            logger.info(f"[{domain}] Page {idx}/{len(pages)}: {page_url}")
        try:
            r = await crawl_with_fallback(page_url, domain=domain)
        except Exception as e:
            logger.error(f"[{domain}] Page {idx} crawl exception: {e}")
            continue

        # İlk sayfa için (homepage), evidence_path ve egress'i agregate'e al
        if idx == 1:
            aggregate["evidence_path"] = r.get("evidence_path")
            aggregate["egress"] = r.get("egress")
            aggregate["http_code"] = r.get("http_code")

        # Page summary
        page_scripts = r.get("injection_scripts", []) or []
        aggregate["page_results"].append({
            "url": page_url,
            "raw_count": len(r.get("raw_hacklinks", []) or []),
            "js_count": len(r.get("js_diff_hacklinks", []) or []),
            "rendered_count": len(r.get("rendered_hacklinks", []) or []),
            "http_code": r.get("http_code"),
            "scripts": [s.get("src", "(inline)") for s in page_scripts],
            "status": r.get("status"),
            "egress": r.get("egress"),
            "cloaking": bool(r.get("cloaking_detected")),
        })
        aggregate["pages_crawled"] += 1

        # Aggregate scripts (unique src bazlı)
        for s in page_scripts:
            src = s.get("src") or s.get("url") or "(inline)"
            if src not in aggregate["unique_scripts"]:
                aggregate["unique_scripts"][src] = {
                    "src": src,
                    "decoded_c2_urls": list(set(s.get("decoded_c2_urls", []) or [])),
                    "pages": [],
                    "snippet": s.get("snippet"),
                }
            if page_url not in aggregate["unique_scripts"][src]["pages"]:
                aggregate["unique_scripts"][src]["pages"].append(page_url)
            # C2 URL'leri merge
            for u in (s.get("decoded_c2_urls") or []):
                if u not in aggregate["unique_scripts"][src]["decoded_c2_urls"]:
                    aggregate["unique_scripts"][src]["decoded_c2_urls"].append(u)

        # Hacklinks dedup
        for hl in (r.get("raw_hacklinks", []) or []):
            h = hl.get("href")
            if h and h not in seen_raw:
                seen_raw.add(h)
                hl["_page"] = page_url
                aggregate["raw_hacklinks"].append(hl)
        for hl in (r.get("js_diff_hacklinks", []) or []):
            h = hl.get("href")
            if h and h not in seen_js:
                seen_js.add(h)
                hl["_page"] = page_url
                aggregate["js_diff_hacklinks"].append(hl)
        for hl in (r.get("rendered_hacklinks", []) or []):
            h = hl.get("href")
            if h and h not in seen_rendered:
                seen_rendered.add(h)
                aggregate["rendered_hacklinks"].append(hl)

        # Cloaking
        if r.get("cloaking_detected"):
            aggregate["cloaking_detected"] = True
            for ev in (r.get("cloaking_evidence") or []):
                if ev not in aggregate["cloaking_evidence"]:
                    aggregate["cloaking_evidence"].append(ev)

    aggregate["injection_scripts"] = list(aggregate["unique_scripts"].values())
    # Total = raw ∪ js (rendered redundant)
    aggregate["total_hacklinks"] = len(aggregate["raw_hacklinks"]) + len(aggregate["js_diff_hacklinks"])

    # Status
    if aggregate["total_hacklinks"] > 0:
        aggregate["status"] = "compromised"
    elif aggregate["cloaking_detected"]:
        aggregate["status"] = "cloaking_detected"
    elif aggregate["http_code"] and aggregate["http_code"] < 400:
        aggregate["status"] = "clean"
    else:
        aggregate["status"] = "unreachable"

    logger.info(
        f"[{domain}] Multi-page crawl tamamlandı: {aggregate['pages_crawled']}/{aggregate['pages_attempted']} sayfa, "
        f"{aggregate['total_hacklinks']} hacklink, {len(aggregate['unique_scripts'])} unique script, "
        f"durum={aggregate['status']}"
    )

    # Aggregate kanıt: evidence/{domain}/analysis/aggregate.json
    try:
        out_dir = Path(settings.evidence_path) / domain / "analysis"
        out_dir.mkdir(parents=True, exist_ok=True)
        agg_clean = {k: v for k, v in aggregate.items() if k not in ("rendered_hacklinks",)}
        (out_dir / "aggregate.json").write_text(
            json.dumps(agg_clean, indent=2, default=str), encoding="utf-8"
        )
        # hacklinks.json'i de aggregate ile güncel tut
        (out_dir / "hacklinks.json").write_text(
            json.dumps({
                "raw_hacklinks": aggregate["raw_hacklinks"],
                "js_diff_hacklinks": aggregate["js_diff_hacklinks"],
                "rendered_hacklinks": aggregate["rendered_hacklinks"],
                "injection_scripts": aggregate["injection_scripts"],
                "cloaking_detected": aggregate["cloaking_detected"],
                "cloaking_evidence": aggregate["cloaking_evidence"],
                "total_hacklinks": aggregate["total_hacklinks"],
                "pages_crawled": aggregate["pages_crawled"],
                "page_results": aggregate["page_results"],
            }, indent=2, default=str), encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"[{domain}] aggregate.json yazma hatası: {e}")

    return aggregate


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
        # Injection verified: ya hacklink bulundu ya cloaking tespit edildi
        site.injection_verified = (
            crawl_result.get("total_hacklinks", 0) > 0
            or bool(crawl_result.get("cloaking_detected"))
        )
        # Status: status logic sonucundaki açık metni kullan
        site.status = crawl_result.get("status", "clean")

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
