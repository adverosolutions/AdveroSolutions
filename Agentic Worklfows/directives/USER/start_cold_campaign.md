# Start Cold Email Campaign

**Purpose:** Launch cold outreach sequence for new leads
**When to use:** After importing leads, ready to start outreach
**Frequency:** As needed (typically after each lead import)

**IMPORTANT:** Roofing uses a different campaign than HVAC/Plumbing/Electrical. The system auto-selects the correct pathway based on industry.

---

## Campaign Pathways

| Industry | SOP | Emails | Duration | Strategy |
|----------|-----|--------|----------|----------|
| HVAC, Plumbing, Electrical | SOP-002 | 3 emails | 7-10 days | AI/automation angle, book a call |
| Roofing | SOP-002R | 4 emails | 7 days + phone escalation | Written-First, generate reply → deliver prototype |

---

## What This Does

### HVAC / Plumbing / Electrical (SOP-002)
1. Validates leads are in "New Lead" stage
2. Creates campaign in Instantly
3. Adds leads to campaign with personalization variables
4. Launches 3-email sequence (Days 1, 4-5, 7-10)
5. Updates CRM: New Lead → Contacted
6. Creates Active_Sequences tracking records

### Roofing (SOP-002R)
1. Validates leads are in "New Lead" stage
2. Creates campaign in Instantly using roofing-specific templates
3. Adds leads to campaign with {firstName} and {companyName} merge tags
4. Launches 4-email sequence (Days 1, 3, 5, 7)
5. Updates CRM: New Lead → Contacted
6. Creates Active_Sequences tracking records
7. On reply → automated sequence delivers prototype link (see handle_reply.md)

---

## Required Tools

- `execution/google_sheets_crm.py` - CRM operations
- `execution/instantly_api.py` - Email sending
- `execution/email_templates.py` - Email content

---

## Input Format

### Option 1: Launch for All New Leads
```
"Start cold campaign for all new leads"
```

### Option 2: Launch for Specific Industry
```
"Start cold campaign for all HVAC leads"
```

### Option 3: Launch for Specific Leads
```
"Start cold campaign for these lead IDs:
LEAD_20260107_001
LEAD_20260107_002
LEAD_20260107_003"
```

### Option 4: Test with Sample
```
"Start cold campaign for 5 test leads"
```

---

## Campaign Configuration

### HVAC / Plumbing / Electrical (SOP-002)

**Sequence Timing:**
- Email 1: Day 1 (immediate)
- Email 2: Day 4-5
- Email 3: Day 7-10

**Email Templates:**
1. **Cold Email 1**: Personalized curiosity hook
2. **Cold Email 2**: AI transformation + scarcity
3. **Cold Email 3**: Breakup + feedback request

**Personalization Variables:**
- `{first_name}` - Lead first name
- `{company_name}` - Company name
- `{industry}` - Industry type
- Custom variables from lead data

### Roofing (SOP-002R)

**Sequence Timing:**
- Email 1: Day 1 (immediate) — starts AFTER automated personalized opener
- Email 2: Day 3
- Email 3: Day 5
- Email 4: Day 7

**Email Templates:**
1. **Roofing Email 1**: Traffic not converting (Day 1) — 124 words
2. **Roofing Email 2**: Referral verification angle (Day 3) — 124 words
3. **Roofing Email 3**: Buying behavior shift (Day 5) — 131 words
4. **Roofing Email 4**: Graceful exit (Day 7) — 117 words

**Roofing-Specific Rules:**
- NO links in any outreach email
- Do NOT use the word "AI"
- No bullet points — pure conversational prose
- Frame as "system" never "website"
- Subject lines must be ambiguous (look like personal email)
- 100-130 words per email
- Prototype link delivered ONLY after reply via automated sequence

**Personalization Variables:**
- `{firstName}` - Lead first name
- `{companyName}` - Company name

**Post-Sequence (No Reply by Day 7):**
- Day 8: Call #1
- Day 10: Call #2
- Day 13: Call #3
- After Day 14 with no movement: Nurture (30-day follow-up)

**Sending Infrastructure (All Verticals):**
- 50 email accounts (round-robin)
- Max 40 emails/account/day
- Spread evenly across sending window

---

## Process

When you trigger this directive:

1. **I validate leads**
   - Check they're in "New Lead" stage
   - Verify required fields present
   - Confirm email format valid

2. **I create Instantly campaign**
   - Campaign name: `Cold_[Industry]_[Date]`
   - Set sequence timing
   - Configure tracking

3. **I add leads to campaign**
   - Upload with all personalization variables
   - Distribute across sender accounts
   - Set first send time

4. **I update CRM**
   - Stage: New Lead → Contacted
   - Log email activity (Email_Activity sheet)
   - Create sequence tracking (Active_Sequences sheet)
   - Record timestamps

5. **I return summary:**

   **HVAC/Plumbing/Electrical example:**
   ```
   ✅ Campaign Launched

   📊 Stats:
      - Campaign: Cold_HVAC_20260107
      - Leads added: 47
      - Sequences active: 47
      - First sends: Within 1 hour
      - Completion: ~10 days

   📧 Email Schedule:
      - Email 1: Today (47 sends)
      - Email 2: Jan 11-12 (auto)
      - Email 3: Jan 14-17 (auto)

   📈 Tracking:
      - View in Instantly: [link]
      - CRM updates: Real-time
      - Reply monitoring: Active

   🚀 Next: Replies will be auto-handled by reply_monitor system
   ```

   **Roofing example:**
   ```
   ✅ Campaign Launched (Roofing — Written-First Pathway)

   📊 Stats:
      - Campaign: Cold_Roofing_20260213
      - Leads added: 52
      - Sequences active: 52
      - First sends: Within 1 hour
      - Completion: Day 7 (phone escalation Days 8-14)

   📧 Email Schedule:
      - Email 1: Today (52 sends) — Traffic angle
      - Email 2: Day 3 — Referral angle
      - Email 3: Day 5 — Buying behavior angle
      - Email 4: Day 7 — Graceful exit

   📈 Tracking:
      - View in Instantly: [link]
      - CRM updates: Real-time
      - Reply monitoring: Active

   🚀 Next: Replies trigger prototype delivery via automated sequence
   ```

---

## Output

You'll see:
- Campaign created confirmation
- Number of leads added
- Send schedule
- Links to monitor progress

---

## Next Actions

After launching:

1. **Monitor in Instantly** - Check campaign dashboard
2. **Watch CRM** - Leads move to Contacted stage
3. **Replies auto-handled** - AI responds within 60s
4. **Check metrics** - Run `check_campaign_stats.md` daily

---

## Edge Cases

### No Leads in "New Lead" Stage
- System will report: "No new leads to contact"
- Solution: Import leads via `add_leads.md` first

### Leads Missing Required Fields
- System skips incomplete leads
- Reports which fields are missing
- You can fix and re-run

### Daily Send Limit Reached
- System queues for next available send window
- Reports estimated send time
- Automatically distributes across days

### Duplicate Campaign Name
- System appends timestamp to make unique
- Continues without error

---

## Campaign Settings

**Deliverability:**
- Warm-up mode: Disabled (assuming accounts pre-warmed)
- SPF/DKIM: Configured per account
- Unsubscribe link: Included in footer
- Bounce handling: Automatic removal

**Tracking:**
- Opens: Tracked
- Clicks: Tracked
- Replies: Monitored every 60s
- Unsubscribes: Instant removal

**Compliance:**
- CAN-SPAM compliant
- Unsubscribe honored immediately
- Physical address in footer
- Industry-specific opt-out handling

---

## Monitoring

**Automated:**
- Reply detection (60s interval)
- Bounce handling
- Unsubscribe processing
- Stage transitions

**Manual Checks:**
- Daily: `check_campaign_stats.md`
- Weekly: Review Instantly dashboard
- As needed: CRM Active_Sequences sheet

---

## Stopping a Campaign

If you need to stop a campaign:

```
"Stop campaign Cold_HVAC_20260107"
```

This will:
- Pause all scheduled sends
- Mark sequences as "stopped" in CRM
- Preserve data for reporting
- Leads remain in current stage

---

## Success Metrics

**Target Benchmarks (per Master SOP):**
- Reply rate: > 1%
- Positive reply rate: > 0.5%
- Booking rate (from engaged): > 65%
- Bounce rate: < 3%

**Alerts trigger if:**
- Reply rate drops below 0.5% for 3 days
- Bounce rate exceeds 5%
- Spam complaints received
- Send volume issues

---

## Example Usage

### Launch for All New Leads
```
User: "Start cold campaign for all new leads"

System:
✅ Found 47 leads in "New Lead" stage
✅ Created campaign: Cold_Mixed_20260107
✅ Added 47 leads to Instantly
✅ Sequences launching...

Campaign active! First emails sending now.
```

### Launch by Industry
```
User: "Start cold campaign for HVAC leads only"

System:
✅ Found 23 HVAC leads
✅ Created campaign: Cold_HVAC_20260107
✅ All leads added successfully

23 sequences active. Monitoring for replies.
```

### Launch Roofing Campaign
```
User: "Start cold campaign for Roofing leads"

System:
✅ Found 52 Roofing leads
✅ Using SOP-002R (Written-First pathway — 4 emails, no AI mentions, no links)
✅ Created campaign: Cold_Roofing_20260213
✅ All leads added successfully

52 sequences active. Replies will trigger prototype delivery.
```

---

## Common Questions

**Q: Can I customize the email templates?**
A: Yes! Edit `execution/email_templates.py` and redeploy.

**Q: What if a lead replies before Email 2 sends?**
A: Sequence auto-stops for that lead. They move to "Engaged" stage.

**Q: Can I test before launching to full list?**
A: Yes! Use "Start campaign for 5 test leads" first.

**Q: How do I know if it's working?**
A: Watch Email_Activity sheet in CRM for real-time logging.

**Q: What happens if Instantly is down?**
A: System retries with exponential backoff, logs errors, alerts you.

---

## Error Handling

If launch fails:
1. Check error in `.tmp/error_log.txt`
2. Verify Instantly API connection
3. Confirm leads have required fields
4. Check daily send limits not exceeded
5. Retry or contact support

Common errors:
- "API authentication failed" → Check Instantly API key
- "No leads found" → Import leads first
- "Daily limit reached" → Wait for next send window
- "Invalid email" → Fix email formats in CRM

---

**Ready to launch your first campaign? Tell me which leads to target!**
