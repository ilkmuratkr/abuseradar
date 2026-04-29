# ICANN DNS Abuse Complaint — Web Form

## Goal
Submit an ICANN compliance complaint about an abuse case at the registrar level. ICANN compliance acts on documented registrar abuse failures (per RAA §3.18).

## Target

- **Domain:** {target_domain}
- **Registrar:** {registrar}
- **Registrar abuse email:** {registrar_abuse_email}
- **First registrar notification:** {report_date}
- **Compromised host pages observed:** {affected_count}
- **Reporter:** AbuseRadar Research, abuse@abuseradar.org

## Steps

1. Navigate to https://www.icann.org/compliance/complaint
2. Choose "Domain Name Compliance / DNS Abuse" complaint type.
3. Fill the form fields with the values above.
4. Paste the **Description** block below into the description / details field.
5. Solve any CAPTCHA. If unsolvable, set `status=captcha_blocked` and stop.
6. Submit. Screenshot the confirmation/ticket page to `/root/workspace/evidence/icann_{target_domain}.png`.
7. Return JSON: `{"status": "submitted" | "captcha_blocked", "ticket_id": "<if shown>"}`.

## Description (paste verbatim)

```
AbuseRadar — Independent web-data observatory.

We are filing a DNS-abuse compliance report regarding {target_domain},
registered through {registrar}. The domain is part of a long-running,
publicly documented SEO-spam injection campaign that has been compromising
government and educational websites since at least January 2025.

Public attribution and prior research:
  - cside Research (Jan 2025, original disclosure):
    https://cside.com/blog/government-and-university-websites-targeted-in-scriptapi-dev-client-side-attack
  - Cyber Security News:
    https://cybersecuritynews.com/javascript-attacks-targeting/
  - Joe Sandbox automated analysis:
    https://www.joesandbox.com/analysis/1684428/0/html
  - PublicWWW live footprint of payload host:
    https://publicwww.com/websites/scriptapi.dev/

The operator group rotates payload hostnames and registers throwaway
destination domains, frequently fronted by major CDNs to obscure hosting.
Per ICANN Registrar Accreditation Agreement §3.18, registrars are required
to investigate and respond to documented abuse reports.

Compromised host pages observed for {target_domain}: {affected_count}
Initial notification to registrar abuse channel ({registrar_abuse_email}):
  {report_date}

This report is being filed because the registrar has not acted on the
documented evidence within the expected response window. Reach the
reporting party at abuse@abuseradar.org for any follow-up.

— AbuseRadar Research (abuseradar.org)
```

## Constraints

- Use only the official `icann.org/compliance/complaint` form.
- Tone: factual, neutral, evidence-based — no hyperbole.
- Time limit: 5 minutes.
