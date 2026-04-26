"""Tehdit istihbarat API entegrasyonları - URLhaus, AbuseIPDB, VirusTotal."""

import logging

import httpx

logger = logging.getLogger(__name__)


async def report_to_urlhaus(url: str, threat_type: str = "malware_download") -> dict:
    """URLhaus'a zararlı URL rapor et."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://urlhaus-api.abuse.ch/v1/url/",
                data={
                    "url": url,
                    "threat": threat_type,
                    "tags": "seo-spam,backlink-injection",
                },
            )
            logger.info(f"URLhaus raporu: {url} → {resp.status_code}")
            return {"status": "submitted", "response_code": resp.status_code}
    except Exception as e:
        logger.error(f"URLhaus hatası: {e}")
        return {"status": "error", "reason": str(e)}


async def report_to_abuseipdb(ip: str, categories: str = "21", comment: str = "") -> dict:
    """AbuseIPDB'ye IP rapor et. Category 21 = Web App Attack."""
    api_key = ""  # .env'den alınacak
    if not api_key:
        return {"status": "skipped", "reason": "api_key_not_set"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.abuseipdb.com/api/v2/report",
                headers={"Key": api_key, "Accept": "application/json"},
                json={
                    "ip": ip,
                    "categories": categories,
                    "comment": comment,
                },
            )
            logger.info(f"AbuseIPDB raporu: {ip} → {resp.status_code}")
            return {"status": "submitted", "response_code": resp.status_code}
    except Exception as e:
        logger.error(f"AbuseIPDB hatası: {e}")
        return {"status": "error", "reason": str(e)}


async def check_virustotal(domain: str) -> dict:
    """VirusTotal'da domain kontrol et."""
    api_key = ""  # .env'den alınacak
    if not api_key:
        return {"status": "skipped", "reason": "api_key_not_set"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"https://www.virustotal.com/api/v3/domains/{domain}",
                headers={"x-apikey": api_key},
            )
            if resp.status_code == 200:
                data = resp.json()
                stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
                return {
                    "status": "checked",
                    "malicious": stats.get("malicious", 0),
                    "suspicious": stats.get("suspicious", 0),
                    "clean": stats.get("harmless", 0),
                }
            return {"status": "error", "response_code": resp.status_code}
    except Exception as e:
        logger.error(f"VirusTotal hatası: {e}")
        return {"status": "error", "reason": str(e)}
