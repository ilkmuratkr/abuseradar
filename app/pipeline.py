"""Ana pipeline - CSV'den sikayete kadar tum akis.

CSV → Parse → Siniflandir → Crawl & Dogrula → Saldirgan Listesi Cikar → Sikayet

KURAL: Crawl ile dogrulanmamis siteye ASLA sikayet veya email gonderme.
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select, text, func, distinct

from models.database import Backlink, Site, DetectedHacklink, async_session

logger = logging.getLogger(__name__)

# Dogrulama icin aranan keyword'ler - sitede BUNLAR varsa enfekte
VERIFICATION_KEYWORDS = [
    # Turkce bahis
    "deneme bonusu", "deneme bonusu veren siteler",
    "casino siteleri", "bahis siteleri",
    "slot siteleri", "canli bahis",
    # Bahis markalari
    "1xbet", "1win", "grandpashabet", "sahabet",
    "onwin", "jojobet", "perabet", "betgaranti",
    "superbet", "betwoon", "radissonbet", "damabet",
    "ritzbet", "exonbet", "ramadabet", "royalbet",
    "cratosroyalbet", "palazzobet", "slotday",
    "spinco", "leogrand",
    # C2 / enjeksiyon imzalari
    "SponsorlinksHTML", "UReferenceLinks",
    "hacklinkbacklink", "backlinksatis",
    "scriptapi.dev", "js_api.php",
    "data-wpl", "insertAdjacentHTML",
    # Diger diller
    "สล็อต", "บาคาร่า",  # Thai slot/baccarat
    "토토사이트", "먹튀검증",  # Korean toto
]


async def run_full_pipeline(auto_crawl: bool = False) -> dict:
    """Tam pipeline: CSV isle → siniflandir → (opsiyonel) crawl → saldirgan listesi cikar.

    Args:
        auto_crawl: True ise dogrulanmamis magdurlari otomatik crawl eder
    """
    results = {}

    # ADIM 1: CSV isle
    logger.info("PIPELINE ADIM 1: CSV isleniyor...")
    from csv_processor.parser import process_inbox
    csv_results = await process_inbox()
    results["csv"] = {
        "processed": len([r for r in csv_results if r["status"] == "completed"]),
        "skipped": len([r for r in csv_results if r["status"] == "skipped"]),
    }

    # ADIM 2: Siniflandir (coklu sinyal)
    logger.info("PIPELINE ADIM 2: Siniflandirma...")
    from classifier.multi_signal import reclassify_all
    classify_results = await reclassify_all()
    results["classification"] = classify_results

    # ADIM 3: Saldirgan domain listesi cikar
    logger.info("PIPELINE ADIM 3: Saldirgan domain listesi cikariliyor...")
    attacker_list = await extract_attacker_domains()
    results["attackers"] = {
        "total": len(attacker_list),
        "sample": attacker_list[:20],
    }

    # ADIM 4: Crawl & dogrula (opsiyonel)
    if auto_crawl:
        logger.info("PIPELINE ADIM 4: Magdur siteler crawl ediliyor...")
        crawl_results = await crawl_unverified_victims(limit=10)
        results["crawl"] = crawl_results
    else:
        results["crawl"] = {"status": "skipped", "reason": "auto_crawl=False"}

    # Ozet
    async with async_session() as session:
        verified = await session.execute(
            text("SELECT count(*) FROM sites WHERE injection_verified = true")
        )
        results["verified_victims"] = verified.scalar() or 0

    logger.info(f"PIPELINE TAMAMLANDI: {results}")
    return results


async def extract_attacker_domains() -> list[dict]:
    """Backlink verilerinden saldirgan domain listesi cikar.

    CSV'deki TARGET domain'ler (backlink'in gittigi yerler) arasinda
    bahis/casino siteleri var - bunlar saldirganin kendi siteleri.

    Ayrica referring site'lardaki anchor text'lerden saldirgan marka/domain'leri cikar.
    """
    async with async_session() as session:
        # 1. Anchor text'te bahis keyword'u olan HEDEF domain'ler
        # Bu domain'ler = saldirganin rank yukseltmek istedigi siteler
        result = await session.execute(
            text("""
                SELECT DISTINCT target_domain, anchor_text,
                       count(*) as backlink_sayisi
                FROM backlinks
                WHERE target_domain IS NOT NULL
                  AND target_domain != ''
                GROUP BY target_domain, anchor_text
                ORDER BY backlink_sayisi DESC
                LIMIT 500
            """)
        )
        all_targets = result.all()

        attackers = []
        seen = set()

        for target_domain, anchor, count in all_targets:
            if not target_domain or target_domain in seen:
                continue

            # Bu domain saldirgan mi? Anchor text'e bak
            anchor_lower = (anchor or "").lower()
            is_gambling_anchor = any(
                kw in anchor_lower for kw in [
                    "deneme bonusu", "bahis", "casino", "slot ",
                    "bet", "grandpashabet", "sahabet", "onwin",
                    "jojobet", "escort", "1xbet", "1win",
                ]
            )

            if is_gambling_anchor:
                gov_edu_tlds = [".gov.", ".gob.", ".edu.", ".ac.", ".gouv."]
                is_gov_edu = any(tld in target_domain for tld in gov_edu_tlds)

                if is_gov_edu:
                    # Gov/edu domain bahis anchor'u ile hedef aliniyor
                    # İki ihtimal: hacklenmiş VEYA tamamen ele geçirilmiş
                    seen.add(target_domain)
                    attackers.append({
                        "domain": target_domain,
                        "anchor_sample": anchor[:100] if anchor else "",
                        "backlink_count": count,
                        "type": "ele_gecirilmis_gov_edu",
                        "severity": "KRITIK",
                        "action": "hosting + registrar + CERT bildir",
                    })
                else:
                    seen.add(target_domain)
                    attackers.append({
                        "domain": target_domain,
                        "anchor_sample": anchor[:100] if anchor else "",
                        "backlink_count": count,
                        "type": "backlink_hedefi",
                    })

        # 2. Referring site'lar arasindaki bilinen saldirgan pattern'ler
        result = await session.execute(
            text("""
                SELECT DISTINCT
                    split_part(split_part(referring_url, '://', 2), '/', 1) as domain,
                    category_detail,
                    count(*) as link_count
                FROM backlinks
                WHERE category = 'SALDIRGAN'
                GROUP BY domain, category_detail
                ORDER BY link_count DESC
                LIMIT 200
            """)
        )
        for domain, detail, count in result.all():
            if domain and domain not in seen:
                seen.add(domain)
                attackers.append({
                    "domain": domain,
                    "type": detail or "saldirgan",
                    "backlink_count": count,
                })

    logger.info(f"Saldirgan domain listesi: {len(attackers)} domain")
    return attackers


async def crawl_unverified_victims(limit: int = 10) -> dict:
    """Henuz crawl edilmemis magdur siteleri crawl et ve dogrula.

    SADECE crawl ile dogrulananlar "verified" olarak isaretlenir.
    Dogrulanmayanlar sikayet pipeline'ina GIRMEZ.
    """
    from crawler.engine import crawl_and_analyze, save_crawl_results

    async with async_session() as session:
        # Magdur olarak siniflandirilmis ama henuz crawl edilmemis siteler
        result = await session.execute(
            text("""
                SELECT DISTINCT
                    split_part(split_part(b.referring_url, '://', 2), '/', 1) as domain,
                    b.referring_url as url
                FROM backlinks b
                LEFT JOIN sites s ON s.domain = split_part(split_part(b.referring_url, '://', 2), '/', 1)
                WHERE b.category = 'MAGDUR'
                  AND (s.last_crawled_at IS NULL OR s.injection_verified IS NULL)
                LIMIT :lim
            """),
            {"lim": limit},
        )
        unverified = result.all()

    if not unverified:
        return {"status": "no_unverified", "crawled": 0}

    logger.info(f"Dogrulanacak magdur: {len(unverified)} site")
    verified = 0
    clean = 0
    errors = 0

    for domain, url in unverified:
        try:
            logger.info(f"[{domain}] Dogrulama crawl basliyor...")
            crawl_result = await crawl_and_analyze(url, domain)
            await save_crawl_results(crawl_result)

            if crawl_result["total_hacklinks"] > 0:
                verified += 1
                logger.info(f"[{domain}] DOGRULANDI: {crawl_result['total_hacklinks']} hacklink")
            else:
                clean += 1
                logger.info(f"[{domain}] TEMIZ: hacklink bulunamadi")

            await asyncio.sleep(5)  # Rate limit

        except Exception as e:
            errors += 1
            logger.error(f"[{domain}] Crawl hatasi: {e}")

    return {
        "status": "completed",
        "crawled": len(unverified),
        "verified_infected": verified,
        "clean": clean,
        "errors": errors,
    }


async def get_pipeline_status() -> dict:
    """Pipeline'in guncel durumunu goster."""
    async with async_session() as session:
        stats = {}

        # CSV durumu
        r = await session.execute(text("SELECT count(*) FROM csv_files WHERE status='completed'"))
        stats["csv_processed"] = r.scalar() or 0

        # Backlink durumu
        r = await session.execute(text("SELECT count(*) FROM backlinks"))
        stats["total_backlinks"] = r.scalar() or 0

        # Siniflandirma durumu
        r = await session.execute(text("""
            SELECT category, count(*) FROM backlinks GROUP BY category
        """))
        stats["classification"] = {row[0]: row[1] for row in r.all()}

        # Dogrulama durumu
        r = await session.execute(text("SELECT count(*) FROM sites WHERE injection_verified = true"))
        stats["verified_victims"] = r.scalar() or 0

        r = await session.execute(text("SELECT count(*) FROM sites WHERE injection_verified = false OR injection_verified IS NULL"))
        stats["unverified"] = r.scalar() or 0

        r = await session.execute(text("SELECT count(*) FROM sites WHERE status = 'remediated'"))
        stats["remediated"] = r.scalar() or 0

        # Hacklink durumu
        r = await session.execute(text("SELECT count(*) FROM detected_hacklinks"))
        stats["detected_hacklinks"] = r.scalar() or 0

        # Sikayet durumu
        r = await session.execute(text("SELECT status, count(*) FROM complaints GROUP BY status"))
        stats["complaints"] = {row[0]: row[1] for row in r.all()}

        # Email durumu
        r = await session.execute(text("SELECT status, count(*) FROM notifications GROUP BY status"))
        stats["notifications"] = {row[0]: row[1] for row in r.all()}

    return stats
