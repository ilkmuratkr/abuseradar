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

# 10 dakikalık görev limiti (form doldurma + LLM call'ları + screenshot
# + CAPTCHA çözmeye çalışma). 5dk Google reCAPTCHA için kısaydı.
DEFAULT_TIMEOUT_SEC = 600


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


async def _run_form_task(
    *,
    task_file: str,
    variables: dict,
    target_domain: str,
    target_type: str,
    platform: str,
    platform_detail: str,
    task_name: str,
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> dict:
    """Tek bir OpenClaw form task'ı için tam akış:
      1. tracker.submit_complaint(status=pending) — duplicate koruma
      2. _render_task → _send_to_openclaw
      3. tracker.mark_complaint_status(submitted/failed) — gerçek sonuç
    Idempotent — already_exists varsa OpenClaw'ı tekrar tetiklemez.
    """
    from .tracker import submit_complaint, mark_complaint_status

    check = await submit_complaint(
        target_domain=target_domain,
        target_type=target_type,
        platform=platform,
        platform_detail=platform_detail,
    )
    if check["status"] == "already_exists":
        return check

    complaint_id = check.get("id")
    task_text = _render_task(task_file, variables)
    result = await _send_to_openclaw(task_text, task_name, timeout=timeout)

    # Status haritalama
    new_status = "failed"
    notes = f"OpenClaw status={result.get('status')}"
    if result.get("status") == "completed":
        rj = result.get("result") or {}
        if rj.get("status") == "submitted":
            new_status = "submitted"
            notes = f"OpenClaw submitted ticket={rj.get('ticket_id')} url={rj.get('form_url')}"
        elif rj.get("status") == "captcha_blocked":
            new_status = "captcha_blocked"
            notes = "CAPTCHA could not be solved"
        elif rj.get("status") == "form_not_available":
            new_status = "form_not_available"
            notes = "No web form available, mailto fallback"
        else:
            new_status = "failed"
            notes = f"Unexpected agent return: {str(rj)[:200]}"
    elif result.get("status") == "timeout":
        new_status = "timeout"
    elif result.get("status") == "error":
        notes = f"OpenClaw error: {result.get('reason', '')[:300]}"

    if complaint_id:
        await mark_complaint_status(complaint_id, new_status=new_status, notes_append=notes)
    result["complaint_id"] = complaint_id
    return result


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
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            except asyncio.TimeoutError:
                stdout, stderr = b"", b""
            partial_out = (stderr or b"").decode(errors="replace")[-2000:]
            logger.error(f"OpenClaw timeout: {task_name} ({timeout}s) — partial={partial_out[-300:]}")
            return {
                "status": "timeout",
                "task_name": task_name,
                "timeout_sec": timeout,
                "partial_output": partial_out,
            }

        # OpenClaw --json envelope'u stderr'e yazıyor. stdout genelde boş.
        # Önce stderr'i, sonra stdout'u tek bir 'out' string'ine birleştir.
        stdout_str = (stdout or b"").decode(errors="replace").strip()
        stderr_str = (stderr or b"").decode(errors="replace").strip()
        out = stderr_str if stderr_str else stdout_str
        err = stdout_str  # debug için

        if proc.returncode != 0:
            logger.warning(f"OpenClaw exit={proc.returncode} task={task_name}: {out[:300]}")
            return {"status": "failed", "exit": proc.returncode, "stderr": out[:500], "stdout": err[:500]}

        # OpenClaw --json output formatı:
        # Outer JSON envelope { "data": { ..., "finalAssistantVisibleText": "<agent cevabı>" } }
        # Stderr'de envelope öncesinde diagnostic log satırları olabilir;
        # son '{' ile başlayan blok'u parse et.
        import re
        result_json: dict | None = None
        agent_text: str | None = None
        envelope: dict | None = None

        # 1. Direct parse
        try:
            envelope = json.loads(out)
        except json.JSONDecodeError:
            # 2. İçerik içindeki son JSON nesnesini bul — '{' ile başlayan
            # ve dengeli kapanan en uzun parça.
            last_brace = out.rfind("\n{")
            if last_brace >= 0:
                candidate = out[last_brace:].strip()
                try:
                    envelope = json.loads(candidate)
                except json.JSONDecodeError:
                    pass
            if envelope is None and out.startswith("{"):
                # Tek satırlık fallback
                try:
                    envelope = json.loads(out)
                except json.JSONDecodeError:
                    pass

        if isinstance(envelope, dict):
            data = envelope.get("data") if isinstance(envelope.get("data"), dict) else envelope
            agent_text = (
                data.get("finalAssistantVisibleText")
                or data.get("finalAssistantRawText")
            )
        else:
            agent_text = out

        if agent_text:
            # Agent text içinde son JSON-benzeri parça
            stripped = agent_text.strip()
            # Markdown ```json ... ``` çıkar
            if "```json" in stripped:
                stripped = stripped.split("```json", 1)[1].split("```", 1)[0].strip()
            elif stripped.startswith("```"):
                stripped = stripped.strip("`").strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    result_json = json.loads(stripped)
                except json.JSONDecodeError:
                    pass

        logger.info(f"OpenClaw tamamlandı: {task_name} → result={result_json}")
        return {
            "status": "completed",
            "task_name": task_name,
            "result": result_json,
            "agent_text": agent_text[:500] if agent_text else None,
            "raw_output": out[:500] if not result_json else None,
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
    report_url: str = "",
) -> dict:
    """Cloudflare abuse formunu OpenClaw ile doldur."""
    return await _run_form_task(
        task_file="cloudflare_abuse.md",
        variables={
            "target_domain": target_domain,
            "target_role": target_role,
            "reporter_email": reporter_email or "abuse@abuseradar.org",
            "affected_gov_sites": affected_gov_sites or "(see report bundle)",
            "injection_method": injection_method,
            "script_endpoint": script_endpoint,
            "affected_count": str(affected_count),
            "first_seen": first_seen,
            "report_url": report_url,
        },
        target_domain=target_domain,
        target_type="attacker",
        platform="cloudflare",
        platform_detail="abuse form",
        task_name=f"cf_{target_domain}",
    )


async def report_google_safebrowsing(*, target_url: str, domain: str, c2_endpoint: str = "") -> dict:
    """Google Safe Browsing — bilinen attacker domain bildir."""
    return await _run_form_task(
        task_file="google_safebrowsing.md",
        variables={"target_url": target_url, "domain": domain, "c2_endpoint": c2_endpoint},
        target_domain=domain,
        target_type="attacker",
        platform="google_safebrowsing",
        platform_detail="safe browsing report",
        task_name=f"gsb_{domain}",
    )


async def report_google_spam(*, target_url: str, domain: str, extra_details: str = "") -> dict:
    """Google Search spam report."""
    return await _run_form_task(
        task_file="google_spam_report.md",
        variables={"target_url": target_url, "domain": domain, "extra_details": extra_details},
        target_domain=domain,
        target_type="attacker",
        platform="google_spam",
        platform_detail="spam report",
        task_name=f"gspam_{domain}",
    )


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
    return await _run_form_task(
        task_file="hosting_abuse_form.md",
        variables={
            "target_domain": target_domain,
            "hosting_provider": hosting_provider or "unknown",
            "abuse_email": abuse_email or "",
            "ip": ip,
            "asn": asn,
            "injection_method": injection_method,
            "hacklink_count": str(hacklink_count),
            "report_url": report_url,
            "reporter_email": reporter_email or "abuse@abuseradar.org",
        },
        target_domain=target_domain,
        target_type="attacker",
        platform="hosting",
        platform_detail=hosting_provider or "unknown",
        task_name=f"hosting_{target_domain}",
    )


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
    return await _run_form_task(
        task_file="registrar_abuse_form.md",
        variables={
            "target_domain": target_domain,
            "registrar": registrar or "unknown",
            "abuse_email": abuse_email or "",
            "target_role": target_role,
            "affected_gov_sites": affected_gov_sites or "(see report bundle)",
            "report_url": report_url,
            "reporter_email": reporter_email or "abuse@abuseradar.org",
        },
        target_domain=target_domain,
        target_type="attacker",
        platform="registrar",
        platform_detail=registrar or "unknown",
        task_name=f"registrar_{target_domain}",
    )


async def report_icann(
    *,
    target_domain: str, registrar: str, registrar_abuse_email: str,
    report_date: str = "", affected_count: int = 1,
) -> dict:
    """ICANN compliance — registrar şikayetlere cevap vermediyse son çare."""
    return await _run_form_task(
        task_file="icann_abuse.md",
        variables={
            "target_domain": target_domain,
            "registrar": registrar,
            "registrar_abuse_email": registrar_abuse_email,
            "report_date": report_date,
            "affected_count": str(affected_count),
        },
        target_domain=target_domain,
        target_type="attacker",
        platform="icann",
        platform_detail="dns abuse compliance",
        task_name=f"icann_{target_domain}",
    )
