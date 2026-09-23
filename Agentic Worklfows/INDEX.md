# AdveroSolutions - System Control Center

**Last Updated:** January 7, 2026
**Status:** 🟢 Operational

---

## 🎯 Quick Access - What You Use Daily

### 📥 Lead Management
- **[Add Leads](directives/USER/add_leads.md)** - Import new leads into CRM
- **[Start Cold Campaign](directives/USER/start_cold_campaign.md)** - Launch 3-email outreach sequence
- **[Fix Lead Stage](directives/USER/fix_lead_stage.md)** - Manually correct lead stage if needed

### 📞 Call Management
- **[Log Discovery Call](directives/USER/log_discovery_call.md)** - Record call outcome & trigger follow-ups

### 📊 Monitoring
- **[Check Campaign Stats](directives/USER/check_campaign_stats.md)** - View performance metrics & health

### 🔧 Edge Cases
- **[Manual Response](directives/USER/manual_response.md)** - Generate custom response for complex replies

---

## ☁️ Automated Systems (Running 24/7)

These run in the cloud via Modal webhooks. **No action needed from you.**

| System | Function | Status |
|--------|----------|--------|
| Reply Monitor | Checks Instantly every 60s for new replies | 🟢 |
| Auto-Responder | Classifies & responds to positive replies | 🟢 |
| Booking Monitor | Tracks calendar bookings | 🟢 |
| No-Show Detector | Triggers recovery when calls missed | 🟢 |
| Sequence Engine | Sends timed follow-ups | 🟢 |
| Campaign Health | Daily metrics & alerts | 🟢 |

**Webhook Status Dashboard:** `https://[your-modal-url]/status`

---

## 📋 System Architecture

```
YOU (Orchestration Layer)
    ↓
Directives (USER/*.md files) ← You trigger these
    ↓
Execution Scripts (Python) ← Deterministic code
    ↓
APIs (Instantly, Claude, Google Sheets)
```

**Cloud systems** use `directives/AUTOMATED/*.md` and run via Modal webhooks without your input.

---

## 🗄️ CRM Structure (Google Sheets)

**Sheet Name:** `AdveroSolutions_CRM`

| Tab | Purpose |
|-----|---------|
| Master_Leads | All lead data + current stage |
| Email_Activity | Sent emails, opens, replies |
| Active_Sequences | Current follow-up sequences |
| Call_Records | Discovery call notes & outcomes |
| Metrics_Dashboard | Daily performance data |

**CRM Link:** [Open CRM](https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID)

---

## 🚨 Troubleshooting

### Something Not Working?

1. **Check Campaign Health**
   Run: `directives/USER/check_campaign_stats.md`

2. **Review Error Logs**
   Check: `.tmp/error_log.txt`

3. **Run Self-Heal**
   Execute: `python execution/self_heal.py`

4. **Manual Override**
   Any automated process can be overridden via USER directives

### Common Issues

| Problem | Solution |
|---------|----------|
| Replies not getting answered | Check Reply Monitor status, verify Instantly API key |
| Sequences not sending | Verify sequence_engine webhook is active |
| CRM not updating | Check Google Sheets API credentials |
| Booking not tracking | Verify calendar integration & permissions |

---

## 📚 Documentation

- **[Quick Start Guide](QUICK_START.md)** - Initial setup instructions
- **[Architecture](Agentic Worklfows/Claude.md)** - How the 3-layer system works
- **[Master SOP](../Downloads/Advero Solutions Master SOP v2.docx)** - Business processes

---

## 🔐 Credentials & API Keys

All sensitive data stored in `.env` (not committed to git):
- Instantly API key
- Claude API key (Anthropic)
- Google Sheets credentials
- Calendar API credentials

**Never commit `.env`, `credentials.json`, or `token.json` to version control.**

---

## 📞 Need Help?

1. Read the relevant `directives/USER/*.md` file
2. Check `.tmp/error_log.txt` for issues
3. Review the execution script in `execution/`
4. System self-heals automatically - give it 5 minutes

---

**Pro Tip:** Bookmark this file. Everything you need starts here.
