# ICANN DNS Abuse Complaint Task

## Goal
Submit a DNS abuse complaint to ICANN about a domain used for cybercrime.

## Domain to Report
{target_domain}

## Steps
1. Navigate to https://www.icann.org/compliance/complaint
2. Select "DNS Abuse" or appropriate complaint type
3. Fill in:
   - Domain name: {target_domain}
   - Registrar: {registrar}
   - Type of abuse: Malware / Phishing
   - Description:

```
Domain {target_domain} is used as Command & Control infrastructure for a 
large-scale SEO spam injection campaign targeting government and educational 
websites worldwide. The domain serves malicious JavaScript that injects 
hidden gambling backlinks into compromised websites.

This abuse was first reported to the registrar ({registrar}) on {report_date} 
but no action has been taken. We are escalating to ICANN.

Registrar abuse contact: {registrar_abuse_email}
Number of affected websites: {affected_count}+
```

4. Submit the complaint
5. Screenshot the confirmation/ticket number
6. Save to /home/node/workspace/evidence/icann_{target_domain}.png
