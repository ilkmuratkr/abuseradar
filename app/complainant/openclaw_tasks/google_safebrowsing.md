# Google Safe Browsing Report Task

## Goal
Report a malicious domain to Google Safe Browsing so Chrome shows a warning.

## URL to Report
{target_url}

## Steps
1. Navigate to https://safebrowsing.google.com/safebrowsing/report_phish/
2. Enter the URL: {target_url}
3. In the additional information field, enter:

```
This domain serves malicious JavaScript used in a large-scale SEO spam 
injection campaign. It has compromised 500+ websites including government 
domains. The script injects hidden gambling backlinks into victim websites.
C2 endpoint: {c2_endpoint}
```

4. Complete any CAPTCHA
5. Submit the report
6. Screenshot the confirmation
7. Save to /home/node/workspace/evidence/safebrowsing_{domain}.png
