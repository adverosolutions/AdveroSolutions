# Quick Start Guide - AdveroSolutions System Setup

**Estimated Setup Time:** 30-45 minutes

---

## 📋 Prerequisites

- [ ] Python 3.9+ installed
- [ ] Google account with Sheets access
- [ ] Instantly account with API access
- [ ] Claude API key (Anthropic account)
- [ ] Calendar system (Google Calendar or Calendly)
- [ ] Modal account (for cloud automation)

---

## 🚀 Setup Steps

### Step 1: Install Dependencies

```bash
cd /Users/lorenzovillarreal/Desktop/AdveroSolutions
pip install -r requirements.txt
```

### Step 2: Configure API Credentials

1. **Copy the environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` and add your API keys:**
   ```
   INSTANTLY_API_KEY=your_instantly_key_here
   ANTHROPIC_API_KEY=your_claude_key_here
   GOOGLE_SHEET_ID=your_sheet_id_here
   CALENDAR_TYPE=google_calendar
   SLACK_WEBHOOK_URL=your_slack_webhook_optional
   ```

3. **Set up Google Sheets API:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create new project: "AdveroSolutions"
   - Enable Google Sheets API
   - Create Service Account credentials
   - Download `credentials.json` to project root
   - Share your CRM sheet with the service account email

### Step 3: Initialize the CRM

Run the CRM initialization script:

```bash
python execution/initialize_crm.py
```

This will:
- Create a new Google Sheet named "AdveroSolutions_CRM"
- Set up all 5 tabs (Master_Leads, Email_Activity, Active_Sequences, Call_Records, Metrics_Dashboard)
- Configure column headers and data validation
- Output the Sheet ID for your `.env` file

**Copy the Sheet ID** and update `GOOGLE_SHEET_ID` in your `.env` file.

### Step 4: Test the System

Run the test suite:

```bash
python execution/test_system.py
```

This validates:
- ✅ Google Sheets connection
- ✅ Instantly API connection
- ✅ Claude API connection
- ✅ Calendar integration
- ✅ CRM read/write operations

### Step 5: Deploy Cloud Automation (Modal)

```bash
# Login to Modal
modal token new

# Deploy webhooks
modal deploy execution/modal_webhook.py
```

After deployment, Modal will output webhook URLs. **Save these URLs** - you'll need them for monitoring.

### Step 6: Verify Automated Systems

Check that all webhooks are running:

```bash
curl https://[your-modal-url]/status
```

You should see all 6 automated systems marked as "active".

---

## 🎯 Your First Campaign

Now you're ready to run your first campaign!

### 1. Add Leads

Open [`directives/USER/add_leads.md`](directives/USER/add_leads.md) and follow the instructions to import your first batch of leads.

### 2. Start Cold Campaign

Open [`directives/USER/start_cold_campaign.md`](directives/USER/start_cold_campaign.md) to launch the 3-email sequence.

### 3. Monitor Performance

Open [`directives/USER/check_campaign_stats.md`](directives/USER/check_campaign_stats.md) to view real-time metrics.

**The automated systems will handle everything else:**
- Replies get answered within 60 seconds
- Bookings get tracked automatically
- No-shows trigger recovery sequences
- Follow-ups send on schedule

---

## 📊 Understanding Your CRM

### Master_Leads Sheet

| Column | Description | Example |
|--------|-------------|---------|
| lead_id | Unique identifier | LEAD_20260107_001 |
| first_name | Contact first name | John |
| last_name | Contact last name | Smith |
| email | Primary email | john@hvacpros.com |
| company_name | Business name | HVAC Pros LLC |
| industry | Vertical | HVAC |
| current_stage | Lead stage | Contacted |
| stage_updated_at | Last stage change | 2026-01-07 14:30:00 |
| created_at | When added to CRM | 2026-01-07 10:15:00 |
| booking_link_sent_at | Calendar link sent time | 2026-01-07 14:30:00 |
| call_scheduled_at | Booking time | 2026-01-08 15:00:00 |
| last_reply_at | Most recent reply | 2026-01-07 14:28:00 |

### Lead Stages (Defined in Master SOP)

1. **New Lead** - Just imported, no outreach yet
2. **Contacted** - In cold email sequence
3. **Engaged** - Positive reply received, booking link sent
4. **Non-Booker** - Has link but hasn't booked (72+ hours)
5. **Booked** - Call scheduled
6. **No-Show** - Missed scheduled call
7. **Discovery Done** - Call completed
8. **Closed Won** - Customer (terminal)
9. **Closed Lost** - Declined/DQ (terminal)

**Rule:** A lead exists in exactly ONE stage at a time.

---

## 🛠️ Daily Workflow

### Morning Routine
1. Check [Campaign Stats](directives/USER/check_campaign_stats.md)
2. Review any alerts in `.tmp/error_log.txt`
3. Add new leads if you have them via [Add Leads](directives/USER/add_leads.md)

### After Discovery Calls
1. Open [Log Discovery Call](directives/USER/log_discovery_call.md)
2. Record outcome (Verbal Commit, Think About It, etc.)
3. System automatically triggers the right follow-up sequence

### Everything Else is Automated
- ✅ Cold emails send on schedule
- ✅ Replies get instant responses
- ✅ Bookings tracked automatically
- ✅ No-shows followed up within 5 minutes
- ✅ Non-bookers get recovery sequence after 72 hours
- ✅ Post-call sequences execute based on outcome

---

## 🔍 Monitoring & Maintenance

### Check System Health

**Daily:** Review [Campaign Stats](directives/USER/check_campaign_stats.md)

**Weekly:** Check Modal webhook logs for errors

**Monthly:** Review and update email templates if performance drops

### Self-Healing System

If something breaks, the system attempts to self-heal:

1. **Detection:** Webhook detects error or anomaly
2. **Analysis:** Execution script identifies root cause
3. **Fix:** Applies known solution from directive knowledge base
4. **Update:** Directive updated with new learnings
5. **Alert:** Slack notification sent (if configured)

### Manual Intervention

If self-healing fails, you'll get an alert. Use these tools:

- **[Fix Lead Stage](directives/USER/fix_lead_stage.md)** - Correct stage errors
- **[Manual Response](directives/USER/manual_response.md)** - Handle edge cases
- **Error Logs:** Check `.tmp/error_log.txt`
- **Run Tests:** `python execution/test_system.py`

---

## 🚨 Troubleshooting Common Issues

### "Google Sheets API authentication failed"

**Solution:**
1. Verify `credentials.json` is in project root
2. Check service account has access to your sheet
3. Re-run: `python execution/test_system.py`

### "Instantly API rate limit exceeded"

**Solution:**
1. Check your Instantly plan limits
2. Adjust send rate in `execution/instantly_api.py`
3. Default: 2000 emails/day spread across 50 accounts

### "Replies not getting answered"

**Solution:**
1. Check Modal webhook status: `https://[your-modal-url]/status`
2. Verify Claude API key in `.env`
3. Check `.tmp/error_log.txt` for API errors

### "Sequences not sending"

**Solution:**
1. Verify `sequence_engine` webhook is active
2. Check Active_Sequences sheet for pending sends
3. Review Instantly account for sending issues

---

## 📚 Next Steps

1. ✅ Complete setup (you just did this!)
2. 📥 Import your first lead list
3. 🚀 Launch first cold campaign
4. 📊 Monitor for 24 hours
5. 🔧 Refine based on metrics
6. 📈 Scale to full volume

---

## 🆘 Need Help?

1. **Start with [INDEX.md](INDEX.md)** - Central navigation
2. **Read the relevant directive** - Each has detailed instructions
3. **Check error logs** - `.tmp/error_log.txt`
4. **Run tests** - `python execution/test_system.py`
5. **Review architecture** - `Agentic Worklfows/Claude.md`

---

**You're all set!** Head to [INDEX.md](INDEX.md) to start using the system.
