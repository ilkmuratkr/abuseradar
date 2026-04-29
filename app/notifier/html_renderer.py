"""Plain text mail body'sini profesyonel HTML email'e dönüştürür.

Email-safe, inline CSS, 600px container, system fonts, brand renkler.
Markdown'a benzer parse: paragraf, '- ' liste, URL, '1. 2. 3.' numbered list.
"""

import html
import re
from typing import Optional

# Brand colors (web sitesindeki ile uyumlu)
BRAND_TEAL = "#1ACEC9"
BRAND_DARK = "#001016"
TEXT = "#1a1a1a"
TEXT_DIM = "#5a6670"
BORDER = "#e3e8ec"
BG_CALLOUT = "#f7f9fa"
ACCENT_AMBER = "#d97706"


def _escape(s: str) -> str:
    return html.escape(s or "", quote=True)


def _is_url_line(line: str) -> bool:
    s = line.strip()
    return s.startswith("http://") or s.startswith("https://")


def _is_list_item(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("- ") or s.startswith("• ") or s.startswith("* ")


def _is_numbered(line: str) -> bool:
    s = line.lstrip()
    return bool(re.match(r"^\d+[.)]\s", s))


def _is_section_header(line: str) -> bool:
    """Kalın başlık niyetiyle yazılmış kısa cümleler:
    'What we observed:', 'Quick verification:', 'Gözlemlediklerimiz:' gibi."""
    s = line.strip()
    return bool(s) and s.endswith(":") and len(s) < 60 and not _is_url_line(s)


def _linkify(text: str) -> str:
    """Plain text URL'lerini <a> tag'ine çevir, geri kalan metni escape et."""
    parts = re.split(r"(https?://\S+)", text)
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:
            href = p.rstrip(".,;:)")
            trail = p[len(href):]
            out.append(f'<a href="{_escape(href)}" style="color:{BRAND_TEAL};text-decoration:underline">{_escape(href)}</a>{_escape(trail)}')
        else:
            out.append(_escape(p))
    return "".join(out)


def render_html_email(text_body: str, *, brand_label: str = "AbuseRadar") -> str:
    """Plain text body'yi profesyonel HTML email'e dönüştür."""
    # Body'yi paragraflara böl (boş satır separator)
    paragraphs = re.split(r"\n\s*\n", text_body.strip())

    body_parts: list[str] = []
    in_callout = False  # Verification block için yellow callout
    callout_lines: list[str] = []

    def flush_callout():
        nonlocal in_callout, callout_lines
        if not callout_lines:
            return
        head = callout_lines[0]
        rest = callout_lines[1:]
        items_html = ""
        # numbered list olanları <ol>'a koy
        nums = [ln for ln in rest if _is_numbered(ln.strip())]
        non_nums = [ln for ln in rest if ln.strip() and not _is_numbered(ln.strip())]
        if nums:
            items_html = "<ol style='margin:8px 0 0;padding-left:20px;color:{}'>".format(TEXT)
            for n in nums:
                stripped = re.sub(r"^\s*\d+[.)]\s*", "", n)
                items_html += f"<li style='margin:4px 0;line-height:1.55'>{_linkify(stripped)}</li>"
            items_html += "</ol>"
        if non_nums:
            items_html += "<div style='margin-top:6px;color:{};font-size:13px;line-height:1.5'>".format(TEXT_DIM)
            items_html += "<br>".join(_linkify(s.strip()) for s in non_nums)
            items_html += "</div>"
        body_parts.append(
            f"""<div style="margin:18px 0;padding:14px 16px;background:{BG_CALLOUT};border-left:3px solid {ACCENT_AMBER};border-radius:0 6px 6px 0">
              <div style="font-size:12px;font-weight:600;color:{ACCENT_AMBER};text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">{_escape(head.rstrip(':'))}</div>
              {items_html}
            </div>"""
        )
        callout_lines = []
        in_callout = False

    def is_verification_header(s: str) -> bool:
        s_low = s.lower().strip().rstrip(":")
        return any(
            kw in s_low for kw in [
                "quick verification", "hızlı doğrulama", "verificación rápida",
                "verificação rápida", "vérification rapide", "schnelle überprüfung",
                "verifica rapida", "быстрая проверка", "التحقق السريع", "快速验证",
            ]
        )

    for para in paragraphs:
        lines = [ln for ln in para.split("\n") if ln.strip()]
        if not lines:
            continue
        first = lines[0].strip()

        # Verification callout başlangıcı
        if is_verification_header(first):
            flush_callout()
            in_callout = True
            callout_lines = lines
            continue

        # Yalnızca URL içeren paragraf → CTA button
        if len(lines) == 1 and _is_url_line(first):
            url = first
            body_parts.append(
                f"""<div style="margin:22px 0">
                  <a href="{_escape(url)}" style="display:inline-block;padding:11px 20px;background:{BRAND_DARK};color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:14px">View technical bundle →</a>
                  <div style="margin-top:8px;font-size:12px;color:{TEXT_DIM};word-break:break-all">{_linkify(url)}</div>
                </div>"""
            )
            continue

        # Bullet list paragrafı (ilk satır başlık + sonraki satırlar - ile başlıyor)
        if any(_is_list_item(ln) for ln in lines[1:]):
            head = lines[0]
            items = [re.sub(r"^\s*[-•*]\s*", "", ln) for ln in lines[1:] if _is_list_item(ln)]
            body_parts.append(f'<p style="margin:14px 0 6px;color:{TEXT};font-weight:600;font-size:14px">{_linkify(head)}</p>')
            body_parts.append(
                f'<ul style="margin:0 0 14px;padding-left:18px;color:{TEXT};font-size:14px;line-height:1.6">'
                + "".join(f'<li style="margin:4px 0">{_linkify(it)}</li>' for it in items)
                + "</ul>"
            )
            continue

        # Section header
        if _is_section_header(first) and len(lines) == 1:
            body_parts.append(f'<h3 style="margin:20px 0 8px;font-size:14px;font-weight:700;color:{TEXT};letter-spacing:.01em">{_linkify(first.rstrip(":"))}</h3>')
            continue

        # Footer/dipnot ('—' ile başlayan)
        if first.startswith("—") and any(t in first.lower() for t in ["abuseradar research", "araştırma"]):
            # imza
            joined = "<br>".join(_linkify(ln) for ln in lines)
            body_parts.append(f'<div style="margin:24px 0 4px;font-size:14px;color:{TEXT};line-height:1.5">{joined}</div>')
            continue
        if first.startswith("—"):
            joined = "<br>".join(_linkify(ln) for ln in lines)
            body_parts.append(f'<div style="margin:18px 0 0;font-size:11px;color:{TEXT_DIM};line-height:1.5;border-top:1px solid {BORDER};padding-top:12px">{joined}</div>')
            continue

        # Normal paragraf
        joined = "<br>".join(_linkify(ln) for ln in lines)
        body_parts.append(f'<p style="margin:12px 0;color:{TEXT};font-size:14px;line-height:1.6">{joined}</p>')

    flush_callout()

    body_html = "\n".join(body_parts)

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f2f4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="width:100%;background:#f0f2f4">
  <tr><td align="center" style="padding:24px 12px">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;background:#ffffff;border:1px solid {BORDER};border-radius:8px;overflow:hidden">
      <tr><td style="padding:18px 24px;border-bottom:1px solid {BORDER};background:#fafbfc">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="width:100%">
          <tr>
            <td style="font-family:Georgia,serif;font-size:17px;font-weight:600;color:{TEXT};letter-spacing:.01em">
              Abuse<span style="color:{BRAND_TEAL};font-style:italic">Radar</span>
            </td>
            <td align="right" style="font-size:11px;color:{TEXT_DIM};text-transform:uppercase;letter-spacing:.08em">
              Web-data observatory
            </td>
          </tr>
        </table>
      </td></tr>
      <tr><td style="padding:24px 28px">
        {body_html}
      </td></tr>
    </table>
    <div style="margin:14px auto 0;font-size:11px;color:{TEXT_DIM};max-width:600px;text-align:center;line-height:1.5">
      Sent from <a href="https://abuseradar.org" style="color:{TEXT_DIM};text-decoration:underline">abuseradar.org</a>
      &nbsp;·&nbsp; Independent web-data observatory
    </div>
  </td></tr>
</table>
</body></html>
"""
