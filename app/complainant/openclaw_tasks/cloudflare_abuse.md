# Cloudflare Abuse Report — Web Form

## Goal
Open https://abuse.cloudflare.com/ and submit a factual, evidence-based abuse report. Use neutral language — no demands, no inflated numbers.

## Target

- **Domain:** {target_domain}
- **Role observed:** {target_role}
- **Reporter name:** AbuseRadar Research
- **Reporter email:** {reporter_email}
- **Affected (compromised) sites observed:** {affected_count}
- **Sample affected sites:** {affected_gov_sites}
- **Injection method:** {injection_method}
- **First observed:** {first_seen}
- **Public technical bundle:** {report_url}

## Steps

1. Navigate to https://abuse.cloudflare.com/
2. Select the abuse category that best matches:
   - Prefer "Phishing" if the domain mimics a brand, otherwise "Other" / "Malware".
   - Do NOT pick "Spam email" — this is web-spam, not email-spam.
3. Fill the reporter fields with the values above.
4. Enter the URL: `https://{target_domain}/`
5. Paste the **Description** block below into the report description.
6. If a CAPTCHA appears, solve it. If unsolvable, set `status=captcha_blocked` and stop.
7. Submit. Capture the confirmation/ticket page screenshot to `/root/workspace/evidence/cloudflare_{target_domain}.png`.
8. Return JSON: `{"status": "submitted" | "captcha_blocked" | "form_changed", "ticket_id": "<if shown>", "form_url": "<final url>"}`.

## Description (paste verbatim)

```
AbuseRadar — Independent web-data observatory.

The domain {target_domain} appears in our public-pages index as the destination of
hidden third-party links injected into otherwise legitimate websites (typical
SEO-spam injection pattern).

Observed:
  - Compromised host pages with anchors to this domain: {affected_count}
  - Sample affected sites: {affected_gov_sites}
  - Injection method: {injection_method}
  - First observed: {first_seen}

The hidden anchors are styled to be invisible to regular visitors but readable
by search engines. The role of {target_domain} in this pattern: {target_role}.

Full technical bundle (screenshots, rendered DOM, file paths) — no sign-in:
  {report_url}

This pattern has been independently documented since January 2025 by multiple
security researchers and is widely reported in public sources, including:
  - cside Research (original disclosure, Jan 2025):
    https://cside.com/blog/government-and-university-websites-targeted-in-scriptapi-dev-client-side-attack
  - Cyber Security News:
    https://cybersecuritynews.com/javascript-attacks-targeting/
  - SiemBiot.eu coverage:
    https://siembiot.eu/en/cyber-security-news/new-javascript-attack-hijacking-government-and-university-websites/28021
  - Joe Sandbox automated analysis:
    https://www.joesandbox.com/analysis/1684428/0/html
  - PublicWWW live footprint:
    https://publicwww.com/websites/scriptapi.dev/

The operator group has been active for over a year, rotating payload hostnames
and increasingly hosting destination domains behind Cloudflare. We submit this
report so the case is visible to your acceptable-use review team. Reach us at
{reporter_email} for any follow-up.

— AbuseRadar Research (abuseradar.org)
```

## Constraints

- Use only the official `abuse.cloudflare.com` form — never 3rd-party trackers.
- No threats, no demands, no inflated counts. State only observed facts.
- Time limit: 5 minutes per task.
