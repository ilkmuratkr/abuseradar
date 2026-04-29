# Registrar Abuse Report — Web Form

## Goal
Find the abuse-reporting page of the domain registrar and submit a complaint via web form (or fall back to mailto).

## Target

- **Reported domain:** {target_domain}
- **Registrar:** {registrar}
- **Registrar abuse email (fallback):** {abuse_email}

## Steps

1. Search Google for: `{registrar} abuse report` (prefer ICANN-listed abuse contact)
2. Open the registrar's official abuse page.
3. If the page contains a web form:
   - Reporter name: `AbuseRadar Research`
   - Reporter email: `{reporter_email}`
   - Subject / title: `Abuse — SEO spam infrastructure: {target_domain}`
   - Category: choose "Malware / Phishing" or "Other abuse"
   - Description: paste the **Description** block below
   - Submit
4. If only mailto: is available, return `form_not_available`.
5. Screenshot to `/root/workspace/evidence/registrar_{target_domain}.png`.
6. Return JSON: `{"status": "submitted" | "form_not_available", "form_url": "...", "ticket_id": "..."}`.

## Description

```
DOMAIN ABUSE REPORT — SEO spam infrastructure

Domain: {target_domain}
Role in attack: {target_role}

This domain is part of a coordinated SEO spam injection campaign that has
compromised hundreds of websites — including government and educational
institutions. The domain functions as a content/script host that delivers
hidden gambling/adult/pharma anchors into compromised pages at runtime.

Affected institutional domains observed:
{affected_gov_sites}

Per ICANN registrar abuse obligations, we request investigation and
appropriate action. Full evidence bundle:

  {report_url}

— AbuseRadar Research ({reporter_email})
```

## Constraints

- Only the registrar's official abuse channel.
- No CAPTCHA bypass attempts.
- Time limit: 5 minutes.
