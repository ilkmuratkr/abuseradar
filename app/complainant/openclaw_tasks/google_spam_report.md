# Google Spam Report Task

## Goal
Report a spam/malicious website to Google using the spam report form.

## URL to Report
{target_url}

## Steps
1. Navigate to https://www.google.com/webmasters/tools/spamreportform
2. Enter the URL: {target_url}
3. In the comments field, enter:

```
This website is part of a large-scale SEO spam network. It injects hidden 
gambling/casino backlinks into compromised websites including government 
and educational domains. The site uses cloaking to show different content 
to Googlebot vs regular users. {extra_details}
```

4. Submit the form
5. Take a screenshot of the confirmation
6. Save to /home/node/workspace/evidence/google_spam_{domain}.png
