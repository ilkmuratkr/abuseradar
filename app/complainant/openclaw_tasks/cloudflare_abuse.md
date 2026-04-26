# Cloudflare Abuse Report Task

## Goal
Go to https://abuse.cloudflare.com/ and submit an abuse report for the domain specified below.

## Domain to Report
{target_domain}

## Report Details
- **Category**: Phishing / Malware
- **Your Name**: AbuseRadar Research Team
- **Your Email**: {reporter_email}
- **URLs**: https://{target_domain}

## Description to Submit
```
SECURITY RESEARCH REPORT - SEO Spam Injection Infrastructure

Domain: {target_domain}
Role: {target_role}

This domain is part of a large-scale SEO spam injection campaign that has compromised 500+ websites globally, including government (.gov) and educational (.edu) domains.

The domain serves malicious JavaScript that injects hidden gambling/casino backlinks into compromised websites. The injected content is invisible to users but indexed by search engines.

Affected government sites include:
{affected_gov_sites}

Technical evidence:
- Injection method: {injection_method}
- Script endpoint: {script_endpoint}
- Number of affected sites: {affected_count}+
- First observed: {first_seen}

We request termination of Cloudflare services for this domain.
```

## Steps
1. Navigate to https://abuse.cloudflare.com/
2. Select the appropriate abuse category
3. Fill in reporter name and email
4. Enter the domain URL
5. Paste the description above into the description field
6. If there is a CAPTCHA, solve it
7. Submit the form
8. Take a screenshot of the confirmation page
9. Save the screenshot to /home/node/workspace/evidence/cloudflare_{target_domain}.png
