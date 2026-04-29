# Hosting Provider Abuse Report — Web Form

## Goal
Find the abuse / TOS-violation reporting page of the hosting provider serving the offending domain and submit a complaint via web form. If no form is reachable, fall back to mailto.

## Target

- **Hosted domain (offender):** {target_domain}
- **Hosting provider:** {hosting_provider}
- **Provider abuse email (fallback):** {abuse_email}
- **Provider IP / ASN:** {ip} / {asn}

## Steps

1. Search Google for: `{hosting_provider} abuse report form`
2. Open the official provider abuse page (only the provider's own domain — never a 3rd-party form).
3. If the page contains a web form:
   - Reporter name: `AbuseRadar Research`
   - Reporter email: `{reporter_email}`
   - Subject / title: `SEO spam injection — {target_domain}`
   - Category: prefer "Malware / Phishing" or "Abuse / TOS violation" (not "Spam email")
   - Description: paste the **Description** block below
   - Submit
4. If the page only lists a mailto: link, stop here and report `form_not_available`.
5. After submit, take a screenshot of the confirmation page and save to `/root/workspace/evidence/hosting_{target_domain}.png`.
6. Return JSON: `{"status": "submitted" | "form_not_available", "form_url": "...", "ticket_id": "..."}`.

## Description

```
SECURITY RESEARCH REPORT — Compromised website hosted on your infrastructure

Domain: {target_domain}
IP: {ip}
ASN: {asn}

We are an independent web-data observatory (abuseradar.org). During a routine
public-data scan we observed that the page at https://{target_domain}/ is
serving JavaScript that injects hidden third-party links into the rendered DOM.

Technical evidence:
- Injection method: {injection_method}
- Number of inserted external anchors: {hacklink_count}
- The links are styled to be invisible to regular visitors but indexable by
  search engines (classic SEO-spam injection pattern).

We are reporting this to your abuse channel because the hosted account is
either compromised or is in violation of your acceptable-use policy. We are
NOT requesting account termination — only that the site owner is notified
and assisted with remediation. Full technical bundle (no sign-in required):

  {report_url}

The same SEO-spam injection pattern has been documented in public security
research since January 2025 (cside, Cyber Security News, Joe Sandbox).

This is a one-time, automated notice. Reach us at {reporter_email} for any
follow-up.

— AbuseRadar Research
```

## Constraints

- Use only the provider's official abuse channel — do NOT submit to forums or 3rd-party trackers.
- If a CAPTCHA blocks submission and you cannot solve it, return `status=captcha_blocked`.
- Never include user accounts/passwords; never contact end-users directly.
- Time limit: 5 minutes per task.
