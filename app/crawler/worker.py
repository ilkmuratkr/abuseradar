"""Crawler worker — Redis kuyruğundan crawl jobs alıp çalıştırır.

App tarafında `/api/crawl/{domain}` endpoint'i Redis listesine LPUSH yapar,
buradaki worker BLPOP ile dinler ve `crawl_and_analyze()` çağırır.
"""

import asyncio
import json
import logging
import sys
import traceback

import redis.asyncio as aioredis

from config import settings
from crawler.engine import crawl_site

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

QUEUE_KEY = "abuseradar:crawl_queue"
STATUS_KEY_PREFIX = "abuseradar:crawl_status:"
STATUS_TTL = 86400  # 1 gün


async def update_status(r, domain: str, status: str, **extra):
    payload = {"status": status, **extra}
    await r.set(STATUS_KEY_PREFIX + domain, json.dumps(payload), ex=STATUS_TTL)


async def process_job(r, url: str):
    domain = url.split("://", 1)[-1].split("/", 1)[0] if "://" in url else url.split("/", 1)[0]
    logger.info(f"[{domain}] Crawl başlıyor: {url}")
    await update_status(r, domain, "running", url=url)
    try:
        result = await crawl_site(url)
        # save to DB (sites + detected_hacklinks)
        try:
            from crawler.engine import save_crawl_results
            await save_crawl_results(result)
        except Exception as e:
            logger.warning(f"[{domain}] DB save uyarısı: {e}")

        await update_status(
            r,
            domain,
            "completed" if result.get("status") != "error" else "error",
            url=url,
            egress=result.get("egress"),
            http_code=result.get("http_code"),
            total_hacklinks=result.get("total_hacklinks", 0),
            pages_crawled=result.get("pages_crawled", 0),
            unique_scripts=len(result.get("unique_scripts", {})),
            evidence_path=result.get("evidence_path"),
            error=result.get("error"),
        )
        logger.info(
            f"[{domain}] Multi-page crawl tamamlandı — pages={result.get('pages_crawled')}, "
            f"hacklinks={result.get('total_hacklinks', 0)}, "
            f"scripts={len(result.get('unique_scripts', {}))}"
        )
    except Exception as e:
        logger.error(f"[{domain}] Crawl hatası: {e}\n{traceback.format_exc()}")
        await update_status(r, domain, "error", url=url, error=str(e))


async def main():
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    logger.info(f"Crawler worker başladı, kuyruk dinleniyor: {QUEUE_KEY}")

    while True:
        try:
            item = await r.blpop(QUEUE_KEY, timeout=30)
            if not item:
                continue
            _, url = item
            await process_job(r, url)
        except asyncio.CancelledError:
            logger.info("Worker iptal sinyali aldı, çıkılıyor.")
            break
        except Exception as e:
            logger.error(f"Worker döngüsü hatası: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
