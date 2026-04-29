"""OpenClaw entegrasyonu — browser-automation skill ile abuse formu doldurma.

OpenClaw VPN-US SOCKS proxy üzerinden çıkar (anonim IP).
LLM çağrıları da VPN-US üzerinden — sunucu IP'si dashboard'lara yansımaz.

CLI: `openclaw agent --local --agent main -m "<task>" --json`
"""

import asyncio
import json
import logging
import os
import shlex
import subprocess
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

TASKS_DIR = Path(__file__).parent / "openclaw_tasks"
OPENCLAW_CONTAINER = os.environ.get("OPENCLAW_CONTAINER", "openclaw")

# 5 dakikalık görev limiti (form doldurma + LLM call'ları + screenshot)
DEFAULT_TIMEOUT_SEC = 300


def _render_task(task_file: str, variables: dict) -> str:
    """Görev şablonunu değişkenlerle doldur."""
    template_path = TASKS_DIR / task_file
    if not template_path.exists():
        raise FileNotFoundError(f"Görev şablonu bulunamadı: {task_file}")
    content = template_path.read_text(encoding="utf-8")
    for key, value in variables.items():
        placeholder = "{" + key + "}"
        content = content.replace(placeholder, str(value))
    return content


async def _send_to_openclaw(task_text: str, task_name: str, timeout: int = DEFAULT_TIMEOUT_SEC) -> dict:
    """OpenClaw agent'ına görev gönder (browser-automation skill aktif).

    `openclaw agent --local --agent main -m "<task>" --json --timeout 300`
    """
    cmd = [
        "docker", "exec", OPENCLAW_CONTAINER,
        "openclaw", "agent",
        "--local", "--agent", "main",
        "--json", "--thinking", "medium",
        "--timeout", str(timeout - 10),
        "-m", task_text,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            logger.error(f"OpenClaw timeout: {task_name} ({timeout}s)")
            return {"status": "timeout", "task_name": task_name}

        out = (stdout or b"").decode(errors="replace").strip()
        err = (stderr or b"").decode(errors="replace").strip()

        if proc.returncode != 0:
            logger.warning(f"OpenClaw exit={proc.returncode} task={task_name}: {err[:300]}")
            return {"status": "failed", "exit": proc.returncode, "stderr": err[:500], "stdout": out[:500]}

        # JSON içerik parse — son satırda olmalı
        result_json: dict | None = None
        for line in reversed(out.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    result_json = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

        logger.info(f"OpenClaw tamamlandı: {task_name}")
        return {
            "status": "completed",
            "task_name": task_name,
            "result": result_json,
            "raw_output": out[:1000] if not result_json else None,
        }

    except Exception as e:
        logger.error(f"OpenClaw exec hatası {task_name}: {e}")
        return {"status": "error", "reason": str(e), "task_name": task_name}


async def report_cloudflare(
    *,
    target_domain: str,
    target_role: str = "SEO spam destination",
    affected_gov_sites: str = "",
    injection_method: str = "JS injection (hidden anchors)",
    script_endpoint: str = "",
    affected_count: int = 1,
    first_seen: str = "",
    reporter_email: str | None = None,
) -> dict:
    """Cloudflare abuse formunu OpenClaw ile doldur."""
    from .tracker import submit_complaint

    check = await submit_complaint(
        target_domain=target_domain,
        target_type="attacker",
        platform="cloudflare",
        platform_detail="abuse form",
    )
    if check["status"] == "already_exists":
        return check

    task = _render_task("cloudflare_abuse.md", {
        "target_domain": target_domain,
        "target_role": target_role,
        "reporter_email": reporter_email or settings.email_reply_to or "abuse@abuseradar.org",
        "affected_gov_sites": affected_gov_sites or "(see report bundle)",
        "injection_method": injection_method,
        "script_endpoint": script_endpoint,
        "affected_count": str(affected_count),
        "first_seen": first_seen,
    })
    return await _send_to_openclaw(task, f"cf_{target_domain}")


async def report_google_safebrowsing(*, target_url: str, domain: str, c2_endpoint: str = "") -> dict:
    """Google Safe Browsing — bilinen attacker domain bildir."""
    from .tracker import submit_complaint

    check = await submit_complaint(
        target_domain=domain, target_type="attacker",
        platform="google_safebrowsing", platform_detail="safe browsing report",
    )
    if check["status"] == "already_exists":
        return check

    task = _render_task("google_safebrowsing.md", {
        "target_url": target_url, "domain": domain, "c2_endpoint": c2_endpoint,
    })
    return await _send_to_openclaw(task, f"gsb_{domain}")


async def report_google_spam(*, target_url: str, domain: str, extra_details: str = "") -> dict:
    """Google Search spam report."""
    from .tracker import submit_complaint

    check = await submit_complaint(
        target_domain=domain, target_type="attacker",
        platform="google_spam", platform_detail="spam report",
    )
    if check["status"] == "already_exists":
        return check

    task = _render_task("google_spam_report.md", {
        "target_url": target_url, "domain": domain, "extra_details": extra_details,
    })
    return await _send_to_openclaw(task, f"gspam_{domain}")


async def report_hosting_form(
    *,
    target_domain: str,
    hosting_provider: str,
    abuse_email: str,
    ip: str,
    asn: str = "",
    injection_method: str = "JS injection",
    hacklink_count: int = 0,
    report_url: str = "",
    reporter_email: str | None = None,
) -> dict:
    """Hosting provider abuse formunu OpenClaw ile bul + doldur."""
    from .tracker import submit_complaint

    check = await submit_complaint(
        target_domain=target_domain, target_type="attacker",
        platform="hosting", platform_detail=hosting_provider or "unknown",
    )
    if check["status"] == "already_exists":
        return check

    task = _render_task("hosting_abuse_form.md", {
        "target_domain": target_domain,
        "hosting_provider": hosting_provider or "unknown",
        "abuse_email": abuse_email or "",
        "ip": ip,
        "asn": asn,
        "injection_method": injection_method,
        "hacklink_count": str(hacklink_count),
        "report_url": report_url,
        "reporter_email": reporter_email or "abuse@abuseradar.org",
    })
    return await _send_to_openclaw(task, f"hosting_{target_domain}")


async def report_registrar_form(
    *,
    target_domain: str,
    registrar: str,
    abuse_email: str,
    target_role: str = "SEO spam infrastructure",
    affected_gov_sites: str = "",
    report_url: str = "",
    reporter_email: str | None = None,
) -> dict:
    """Registrar abuse formunu OpenClaw ile bul + doldur."""
    from .tracker import submit_complaint

    check = await submit_complaint(
        target_domain=target_domain, target_type="attacker",
        platform="registrar", platform_detail=registrar or "unknown",
    )
    if check["status"] == "already_exists":
        return check

    task = _render_task("registrar_abuse_form.md", {
        "target_domain": target_domain,
        "registrar": registrar or "unknown",
        "abuse_email": abuse_email or "",
        "target_role": target_role,
        "affected_gov_sites": affected_gov_sites or "(see report bundle)",
        "report_url": report_url,
        "reporter_email": reporter_email or "abuse@abuseradar.org",
    })
    return await _send_to_openclaw(task, f"registrar_{target_domain}")


async def report_icann(
    *,
    target_domain: str, registrar: str, registrar_abuse_email: str,
    report_date: str = "", affected_count: int = 1,
) -> dict:
    """ICANN compliance — registrar şikayetlere cevap vermediyse son çare."""
    from .tracker import submit_complaint

    check = await submit_complaint(
        target_domain=target_domain, target_type="attacker",
        platform="icann", platform_detail="dns abuse compliance",
    )
    if check["status"] == "already_exists":
        return check

    task = _render_task("icann_abuse.md", {
        "target_domain": target_domain,
        "registrar": registrar,
        "registrar_abuse_email": registrar_abuse_email,
        "report_date": report_date,
        "affected_count": str(affected_count),
    })
    return await _send_to_openclaw(task, f"icann_{target_domain}")
