"""Minimal Playwright form-fill agent — OpenClaw'a alternatif.

Crawler container'ında Playwright + Chromium kurulu. App container'dan
'docker exec crawler python -m complainant.playwright_filler ...' ile
çağrılır (OpenClaw modeli gibi).

Her platform için sabit selector + field mapping. CAPTCHA varsa
status=captcha_blocked döner. CF abuse, Google Safe Browsing, ICANN
form'ları için.
"""

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

EVIDENCE_DIR = Path(os.environ.get("EVIDENCE_DIR", "/data/openclaw-workspace/evidence"))
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


async def _new_page(playwright, *, vpn_proxy: str | None = None):
    """VPN-US SOCKS proxy üzerinden Chromium başlat."""
    launch_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ]
    proxy = None
    if vpn_proxy:
        proxy = {"server": vpn_proxy}
    browser = await playwright.chromium.launch(headless=True, args=launch_args, proxy=proxy)
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )
    page = await context.new_page()
    return browser, context, page


async def fill_cloudflare_abuse(
    *,
    target_domain: str,
    description: str,
    reporter_email: str = "abuse@abuseradar.org",
    reporter_name: str = "AbuseRadar Research",
) -> dict:
    """Cloudflare abuse formunu doldur."""
    from playwright.async_api import async_playwright

    out_png = EVIDENCE_DIR / f"cloudflare_{target_domain}.png"
    async with async_playwright() as p:
        browser, ctx, page = await _new_page(p)
        try:
            await page.goto("https://abuse.cloudflare.com/general", wait_until="domcontentloaded", timeout=45000)
            # Kategori seçimi: 'Other' tipi (web-spam için)
            try:
                # Form yapısı değişebilir; 'reporter_name' input'larını arayalım
                await page.fill('input[name="reporter_name"], input#reporter-name', reporter_name)
            except Exception:
                pass
            try:
                await page.fill('input[name="reporter_email"], input[type="email"]', reporter_email)
            except Exception:
                pass
            try:
                await page.fill('textarea[name="urls"], textarea[name="url"], input[name="url"]', f"https://{target_domain}/")
            except Exception:
                pass
            try:
                await page.fill('textarea[name="description"], textarea[name="content"]', description)
            except Exception:
                pass

            await page.screenshot(path=str(out_png), full_page=True)

            # CAPTCHA tespit
            html = await page.content()
            has_captcha = "g-recaptcha" in html or "cf-turnstile" in html or "hcaptcha" in html
            if has_captcha:
                return {"status": "captcha_blocked", "screenshot": str(out_png)}

            # Submit dene
            try:
                await page.click('button[type="submit"], input[type="submit"]', timeout=8000)
                await page.wait_for_load_state("networkidle", timeout=20000)
                final_url = page.url
                final_png = EVIDENCE_DIR / f"cloudflare_{target_domain}_after.png"
                await page.screenshot(path=str(final_png), full_page=True)
                return {"status": "submitted", "form_url": final_url, "screenshot": str(final_png)}
            except Exception as e:
                return {"status": "submit_failed", "reason": str(e)[:200], "screenshot": str(out_png)}
        except Exception as e:
            return {"status": "error", "reason": str(e)[:200]}
        finally:
            await ctx.close()
            await browser.close()


async def fill_google_safebrowsing(
    *,
    target_url: str,
    description: str,
    reporter_email: str = "abuse@abuseradar.org",
) -> dict:
    """Google Safe Browsing report_phish formunu doldur."""
    from playwright.async_api import async_playwright

    domain = target_url.split("//")[-1].split("/")[0]
    out_png = EVIDENCE_DIR / f"safebrowsing_{domain}.png"
    async with async_playwright() as p:
        browser, ctx, page = await _new_page(p)
        try:
            await page.goto("https://safebrowsing.google.com/safebrowsing/report_phish/", wait_until="domcontentloaded", timeout=45000)
            try:
                await page.fill('input[name="url"], input[type="url"]', target_url)
            except Exception:
                pass
            try:
                await page.fill('textarea[name="comments"], textarea', description)
            except Exception:
                pass
            try:
                await page.fill('input[name="email"], input[type="email"]', reporter_email)
            except Exception:
                pass

            await page.screenshot(path=str(out_png), full_page=True)
            html = await page.content()
            if "g-recaptcha" in html or "captcha" in html.lower():
                return {"status": "captcha_blocked", "screenshot": str(out_png)}

            try:
                await page.click('button[type="submit"], input[type="submit"]', timeout=8000)
                await page.wait_for_load_state("networkidle", timeout=20000)
                final_png = EVIDENCE_DIR / f"safebrowsing_{domain}_after.png"
                await page.screenshot(path=str(final_png), full_page=True)
                return {"status": "submitted", "form_url": page.url, "screenshot": str(final_png)}
            except Exception as e:
                return {"status": "submit_failed", "reason": str(e)[:200], "screenshot": str(out_png)}
        except Exception as e:
            return {"status": "error", "reason": str(e)[:200]}
        finally:
            await ctx.close()
            await browser.close()


# ─── CLI entry — `docker exec crawler python -m complainant.playwright_filler` ────────
async def _cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=["cloudflare", "google_sb"])
    parser.add_argument("--target", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--reporter-email", default="abuse@abuseradar.org")
    parser.add_argument("--reporter-name", default="AbuseRadar Research")
    args = parser.parse_args()

    if args.platform == "cloudflare":
        result = await fill_cloudflare_abuse(
            target_domain=args.target,
            description=args.description,
            reporter_email=args.reporter_email,
            reporter_name=args.reporter_name,
        )
    elif args.platform == "google_sb":
        result = await fill_google_safebrowsing(
            target_url=args.target if args.target.startswith("http") else f"https://{args.target}/",
            description=args.description,
            reporter_email=args.reporter_email,
        )

    # Tek satır JSON stdout — caller parse eder
    print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(_cli())
