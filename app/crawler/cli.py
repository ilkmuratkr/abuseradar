"""Crawler CLI - tek site veya toplu crawl."""

import asyncio
import logging
import sys

from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def crawl_single(url: str):
    """Tek bir siteyi crawl et."""
    from .engine import crawl_with_fallback as crawl_and_analyze, save_crawl_results

    result = await crawl_and_analyze(url)

    print(f"\n{'='*60}")
    print(f"Crawl Sonucu: {result['domain']}")
    print(f"{'='*60}")
    print(f"Durum: {result['status']}")
    print(f"Toplam hacklink: {result['total_hacklinks']}")
    print(f"  Raw HTML'de: {len(result['raw_hacklinks'])}")
    print(f"  Rendered DOM'da: {len(result['rendered_hacklinks'])}")
    print(f"  JS diff: {len(result['js_diff_hacklinks'])}")
    print(f"  Enjeksiyon script: {len(result['injection_scripts'])}")
    print(f"Kanıt: {result['evidence_path']}")

    if result["total_hacklinks"] > 0:
        print(f"\nİlk 10 hacklink:")
        all_hl = result["raw_hacklinks"] + result["rendered_hacklinks"]
        for hl in all_hl[:10]:
            print(f"  [{hl.get('score', 0)}] {hl.get('text', '')[:60]} → {hl.get('href', '')[:80]}")

    if result["injection_scripts"]:
        print(f"\nEnjeksiyon scriptleri:")
        for inj in result["injection_scripts"]:
            print(f"  Patterns: {inj.get('patterns', [])}")
            if inj.get("decoded_c2_urls"):
                print(f"  C2 URLs: {inj['decoded_c2_urls']}")

    # DB'ye kaydet
    await save_crawl_results(result)
    print(f"\nSonuçlar DB'ye kaydedildi.")

    return result


async def crawl_victims():
    """DB'deki tüm mağdur siteleri crawl et."""
    from sqlalchemy import select
    from models.database import async_session, Backlink

    from .engine import crawl_with_fallback as crawl_and_analyze, save_crawl_results

    async with async_session() as session:
        result = await session.execute(
            select(Backlink.referring_url)
            .where(Backlink.category == "MAGDUR")
            .distinct()
            .limit(50)
        )
        urls = [r[0] for r in result.all()]

    print(f"{len(urls)} mağdur site crawl edilecek...")

    for i, url in enumerate(urls):
        print(f"\n[{i+1}/{len(urls)}] {url}")
        try:
            crawl_result = await crawl_and_analyze(url)
            await save_crawl_results(crawl_result)
        except Exception as e:
            print(f"  HATA: {e}")
        await asyncio.sleep(settings.crawl_same_domain_delay)


if __name__ == "__main__":
    from config import settings

    if len(sys.argv) > 1:
        url = sys.argv[1]
        asyncio.run(crawl_single(url))
    else:
        print("Kullanım:")
        print("  python -m crawler.cli <URL>           # Tek site crawl")
        print("  python -m crawler.cli --victims       # Tüm mağdurları crawl")
        if len(sys.argv) > 1 and sys.argv[1] == "--victims":
            asyncio.run(crawl_victims())
