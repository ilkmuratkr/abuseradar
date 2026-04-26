"""OpenClaw entegrasyonu - otonom form doldurma ve şikayet gönderme.

OpenClaw VPN-US SOCKS proxy üzerinden çıkar.
Tüm form doldurma görevleri OpenClaw'a delege edilir.
"""

import json
import logging
import subprocess
from pathlib import Path
from string import Template

from config import settings

logger = logging.getLogger(__name__)

TASKS_DIR = Path(__file__).parent / "openclaw_tasks"
OPENCLAW_CONTAINER = "openclaw"


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


def _send_to_openclaw(task_text: str, task_name: str) -> dict:
    """OpenClaw konteynerine görev gönder.

    OpenClaw'un CLI veya API'si üzerinden görev verir.
    """
    # Görev dosyasını workspace'e yaz
    task_path = f"/home/node/workspace/tasks/active_{task_name}.md"

    try:
        # Görev dosyasını container'a yaz
        write_cmd = [
            "docker", "exec", OPENCLAW_CONTAINER,
            "bash", "-c",
            f"mkdir -p /home/node/workspace/tasks && cat > {task_path}",
        ]
        proc = subprocess.run(
            write_cmd,
            input=task_text,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if proc.returncode != 0:
            logger.error(f"OpenClaw görev yazma hatası: {proc.stderr}")
            return {"status": "error", "reason": proc.stderr}

        # OpenClaw CLI ile görevi çalıştır
        exec_cmd = [
            "docker", "exec", OPENCLAW_CONTAINER,
            "openclaw", "run", task_path,
        ]
        result = subprocess.run(
            exec_cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 dakika max (form doldurma + CAPTCHA)
        )

        if result.returncode == 0:
            logger.info(f"OpenClaw görevi tamamlandı: {task_name}")
            return {"status": "completed", "output": result.stdout[:1000]}
        else:
            logger.warning(f"OpenClaw görevi başarısız: {task_name} → {result.stderr[:500]}")
            return {"status": "failed", "error": result.stderr[:500]}

    except subprocess.TimeoutExpired:
        logger.error(f"OpenClaw görevi timeout: {task_name}")
        return {"status": "timeout", "reason": "5 dakika aşıldı"}
    except Exception as e:
        logger.error(f"OpenClaw hatası: {e}")
        return {"status": "error", "reason": str(e)}


async def report_cloudflare(
    target_domain: str,
    target_role: str,
    reporter_email: str,
    affected_gov_sites: str,
    injection_method: str,
    script_endpoint: str,
    affected_count: int,
    first_seen: str,
) -> dict:
    """Cloudflare abuse formunu OpenClaw ile doldur."""
    from .tracker import submit_complaint

    # Duplicate kontrol
    check = await submit_complaint(
        target_domain=target_domain,
        target_type="c2",
        platform="cloudflare",
        platform_detail="abuse form",
    )
    if check["status"] == "already_exists":
        logger.info(f"CF şikayet zaten var: {target_domain}")
        return check

    task_text = _render_task("cloudflare_abuse.md", {
        "target_domain": target_domain,
        "target_role": target_role,
        "reporter_email": reporter_email,
        "affected_gov_sites": affected_gov_sites,
        "injection_method": injection_method,
        "script_endpoint": script_endpoint,
        "affected_count": str(affected_count),
        "first_seen": first_seen,
    })

    result = _send_to_openclaw(task_text, f"cf_{target_domain}")
    return result


async def report_google_spam(
    target_url: str,
    domain: str,
    extra_details: str = "",
) -> dict:
    """Google spam formunu OpenClaw ile doldur."""
    from .tracker import submit_complaint

    check = await submit_complaint(
        target_domain=domain,
        target_type="spam",
        platform="google_spam",
        platform_detail="spam report form",
    )
    if check["status"] == "already_exists":
        return check

    task_text = _render_task("google_spam_report.md", {
        "target_url": target_url,
        "domain": domain,
        "extra_details": extra_details,
    })

    return _send_to_openclaw(task_text, f"gspam_{domain}")


async def report_google_safebrowsing(
    target_url: str,
    domain: str,
    c2_endpoint: str = "",
) -> dict:
    """Google Safe Browsing formunu OpenClaw ile doldur."""
    from .tracker import submit_complaint

    check = await submit_complaint(
        target_domain=domain,
        target_type="c2",
        platform="google_safebrowsing",
        platform_detail="safe browsing report",
    )
    if check["status"] == "already_exists":
        return check

    task_text = _render_task("google_safebrowsing.md", {
        "target_url": target_url,
        "domain": domain,
        "c2_endpoint": c2_endpoint,
    })

    return _send_to_openclaw(task_text, f"gsb_{domain}")


async def report_icann(
    target_domain: str,
    registrar: str,
    registrar_abuse_email: str,
    report_date: str,
    affected_count: int,
) -> dict:
    """ICANN DNS abuse formunu OpenClaw ile doldur."""
    from .tracker import submit_complaint

    check = await submit_complaint(
        target_domain=target_domain,
        target_type="c2",
        platform="icann",
        platform_detail="dns abuse complaint",
    )
    if check["status"] == "already_exists":
        return check

    task_text = _render_task("icann_abuse.md", {
        "target_domain": target_domain,
        "registrar": registrar,
        "registrar_abuse_email": registrar_abuse_email,
        "report_date": report_date,
        "affected_count": str(affected_count),
    })

    return _send_to_openclaw(task_text, f"icann_{target_domain}")


async def run_all_complaints_for_c2(c2_domain: str, evidence: dict) -> dict:
    """Tek bir C2 domain için tüm şikayet formlarını doldur."""
    results = {}

    # 1. Cloudflare
    results["cloudflare"] = await report_cloudflare(
        target_domain=c2_domain,
        target_role=evidence.get("role", "C2 panel"),
        reporter_email=settings.email_from,
        affected_gov_sites=evidence.get("gov_sites", ""),
        injection_method=evidence.get("method", "JavaScript injection"),
        script_endpoint=evidence.get("endpoint", ""),
        affected_count=evidence.get("affected_count", 500),
        first_seen=evidence.get("first_seen", ""),
    )

    # 2. Google Safe Browsing
    results["safebrowsing"] = await report_google_safebrowsing(
        target_url=f"https://{c2_domain}/",
        domain=c2_domain,
        c2_endpoint=evidence.get("endpoint", ""),
    )

    # 3. ICANN (registrar aksiyon almadıysa)
    if evidence.get("registrar"):
        results["icann"] = await report_icann(
            target_domain=c2_domain,
            registrar=evidence.get("registrar", ""),
            registrar_abuse_email=evidence.get("registrar_abuse", ""),
            report_date=evidence.get("report_date", ""),
            affected_count=evidence.get("affected_count", 500),
        )

    logger.info(f"[{c2_domain}] Tüm şikayetler gönderildi: {results}")
    return results
