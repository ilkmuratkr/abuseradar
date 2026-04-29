# Google Safe Browsing — Phishing/Malware Report

## Goal
Submit `{target_url}` to Google Safe Browsing as part of an SEO-spam injection campaign so Chrome and Search can flag it.

## Target

- **URL to report:** {target_url}
- **Domain:** {domain}
- **Optional C2 endpoint observed:** {c2_endpoint}

## Steps

1. Navigate to https://safebrowsing.google.com/safebrowsing/report_phish/
2. Enter the URL: `{target_url}`
3. Paste the **Additional details** block below.
4. Solve the reCAPTCHA if present. If unsolvable, set `status=captcha_blocked`.
5. Submit. Screenshot the confirmation to `/root/workspace/evidence/safebrowsing_{domain}.png`.
6. Return JSON: `{"status": "submitted" | "captcha_blocked", "form_url": "<final url>"}`.

## Additional details (paste verbatim)

```
Reported by AbuseRadar (abuseradar.org), an independent web-data observatory.

The domain {domain} appears as a destination for hidden anchors injected
into legitimate websites via SEO-spam injection (gambling/casino landing
pages). The anchors are styled to be invisible to users but readable by
search engines, harming the host site's reputation and Google search quality.

C2 endpoint observed (if any): {c2_endpoint}

Reporter contact: abuse@abuseradar.org
```
