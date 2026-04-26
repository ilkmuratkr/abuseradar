"""VPN üzerinden dış istek yapma - API key'ler ASLA doğrudan çıkmaz.

Mimari: app/crawler → VPN container'ına exec → curl → dış dünya
Bu sayede API key'ler sadece VPN tünelinden geçer.

Alternatif olarak VPN container'larında SOCKS proxy kurulabilir ama
exec yaklaşımı daha basit ve güvenli.
"""

import json
import logging
import subprocess

logger = logging.getLogger(__name__)


def request_via_vpn(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    data: str | None = None,
    vpn: str = "vpn-us",
    timeout: int = 30,
) -> dict:
    """VPN container'ı üzerinden HTTP istek yap.

    Args:
        url: Hedef URL
        method: HTTP metodu
        headers: HTTP header'ları
        data: POST body
        vpn: VPN container adı (vpn-us veya vpn-tr)
        timeout: Timeout saniye

    Returns:
        {"status_code": int, "body": str, "error": str | None}
    """
    cmd = ["docker", "exec", vpn, "curl", "-s", "--max-time", str(timeout)]

    if method == "POST":
        cmd.extend(["-X", "POST"])

    if headers:
        for k, v in headers.items():
            cmd.extend(["-H", f"{k}: {v}"])

    if data:
        cmd.extend(["-d", data])

    # Response code'u da al
    cmd.extend(["-w", "\n%{http_code}"])
    cmd.append(url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        output = result.stdout.strip()

        if not output:
            return {"status_code": 0, "body": "", "error": result.stderr}

        # Son satır status code
        lines = output.rsplit("\n", 1)
        body = lines[0] if len(lines) > 1 else output
        status_code = int(lines[-1]) if len(lines) > 1 and lines[-1].isdigit() else 0

        return {"status_code": status_code, "body": body, "error": None}

    except subprocess.TimeoutExpired:
        return {"status_code": 0, "body": "", "error": "timeout"}
    except Exception as e:
        return {"status_code": 0, "body": "", "error": str(e)}


def gemini_via_vpn(prompt: str, api_key: str, model: str = "gemini-2.5-pro") -> str:
    """Gemini API'yi VPN-US üzerinden çağır."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 500},
    })

    result = request_via_vpn(
        url=url,
        method="POST",
        headers={"Content-Type": "application/json"},
        data=payload,
        vpn="vpn-us",
        timeout=60,
    )

    if result["error"]:
        logger.error(f"Gemini VPN hatası: {result['error']}")
        return ""

    try:
        resp = json.loads(result["body"])
        return resp["candidates"][0]["content"]["parts"][0]["text"]
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error(f"Gemini parse hatası: {e}")
        return ""
