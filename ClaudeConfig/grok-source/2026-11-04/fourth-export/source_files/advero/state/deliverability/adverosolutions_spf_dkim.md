# adverosolutions.com SPF + DKIM (Lorenzo delegated 11/2 10:29 AM CT: "you can add that stuff and take care of it if it makes sense")
Status: NOT yet applied. Needs a browser session on Namecheap + Google Admin.
Current (Deliverability, 11/2 10:05 AM CT): no SPF, no DKIM, MX smtp.google.com, DMARC p=none, DNS = Namecheap BasicDNS.

## 1. SPF (Namecheap)
1. namecheap.com > Domain List > adverosolutions.com > Manage > Advanced DNS.
2. Confirm there is no existing TXT starting with v=spf1 (only google-site-verification exists; leave it).
3. Add New Record: Type TXT Record, Host `@`, Value `v=spf1 include:_spf.google.com ~all`, TTL Automatic. Save (green check).

## 2. DKIM (Google Admin, then Namecheap)
1. admin.google.com > Apps > Google Workspace > Gmail > Authenticate email.
2. Select domain adverosolutions.com > Generate new record: key length 2048, prefix selector `google`. Generate.
3. Copy the TXT value (starts `v=DKIM1; k=rsa; p=...`).
4. Namecheap Advanced DNS > Add New Record: TXT, Host `google._domainkey`, Value = the copied string (one line, no quotes), TTL Automatic. Save.
   If Namecheap rejects the 2048-bit value, regenerate at 1024-bit and use that instead.
5. Wait 15-60 min, then back in Google Admin click Start authentication. Status should read "Authenticating email with DKIM".

## 3. Verify
- `dig +short TXT adverosolutions.com @8.8.8.8` shows the v=spf1 line.
- `dig +short TXT google._domainkey.adverosolutions.com @8.8.8.8` shows v=DKIM1.
- Send a test from [EMAIL] to a Gmail; Show original = SPF PASS, DKIM PASS.
- Leave DMARC at p=none until both pass for a week. Deliverability Specialist rechecks.
