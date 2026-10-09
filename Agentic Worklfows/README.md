# AdveroSolutions - AI Automation Agency

**Master Lead Generation, Sales & Follow-Up System**

Fully automated outreach, response, and follow-up system built on the 3-layer architecture: Directives → Orchestration → Execution.

---

## 🚀 Quick Start

1. **Read [QUICK_START.md](QUICK_START.md)** - Complete setup guide
2. **Configure credentials** - Copy `.env.example` to `.env` and add API keys
3. **Initialize CRM** - Run `python execution/initialize_crm.py`
4. **Deploy automation** - Run `modal deploy execution/modal_webhook.py`
5. **Start using** - Open [INDEX.md](INDEX.md) for daily operations

---

## 📋 What This System Does

### Automated (24/7 Cloud Execution)
- ✅ **Reply Monitoring** - Checks Instantly every 60s for new replies
- ✅ **Auto-Response** - AI-generated responses within 60 seconds
- ✅ **Booking Tracking** - Monitors calendar for new bookings
- ✅ **No-Show Recovery** - Instant follow-up when calls are missed
- ✅ **Sequence Execution** - Sends timed follow-ups automatically
- ✅ **Health Monitoring** - Daily metrics & alerts

### User-Triggered (You Control)
- 📥 **Add Leads** - Import new prospects
- 🚀 **Launch Campaigns** - Start cold outreach sequences
- 📞 **Log Calls** - Record discovery call outcomes
- 📊 **Check Stats** - View performance metrics
- 🔧 **Manual Override** - Handle edge cases

---

## 🏗️ Architecture

```
Layer 1: DIRECTIVES (What to do)
├── USER/ - Files you trigger
│   ├── add_leads.md
│   ├── start_cold_campaign.md
│   ├── log_discovery_call.md
│   └── check_campaign_stats.md
│
└── AUTOMATED/ - Cloud system instructions
    ├── reply_monitor.md
    ├── auto_responder.md
    └── sequence_engine.md

Layer 2: ORCHESTRATION (Decision making)
└── Claude API (Opus 5.5, claude-opus-5-5) - Intelligent routing & error handling

Layer 3: EXECUTION (Doing the work)
├── google_sheets_crm.py - CRM operations
├── instantly_api.py - Email sending
├── claude_response.py - AI response generation
└── modal_webhook.py - Cloud automation
```

---

## 📊 Tech Stack

- **CRM:** Google Sheets (5-sheet structure)
- **Email:** Instantly (50 accounts, 2000 emails/day)
- **AI:** Claude API (Opus 5.5, claude-opus-5-5)
- **Cloud:** Modal (serverless webhooks)
- **Language:** Python 3.9+
- **Calendar:** Google Calendar or Calendly

---

## 🗄️ CRM Structure

| Sheet | Purpose | Records |
|-------|---------|---------|
| Master_Leads | All lead data + current stage | ~10K leads |
| Email_Activity | Sent emails, opens, replies | ~50K activities |
| Active_Sequences | Current follow-up sequences | ~1K active |
| Call_Records | Discovery call notes | ~500 calls |
| Metrics_Dashboard | Daily performance data | Rolling 90 days |

---

## 📈 Lead Stages (Master SOP)

1. **New Lead** → Just imported
2. **Contacted** → In cold email sequence
3. **Engaged** → Replied positively, has booking link
4. **Non-Booker** → Has link 72+ hours, hasn't booked
5. **Booked** → Call scheduled
6. **No-Show** → Missed call
7. **Discovery Done** → Call completed
8. **Closed Won** → Customer (terminal)
9. **Closed Lost** → Declined (terminal)

**Rule:** Each lead exists in exactly ONE stage at a time.

---

## 🔄 Email Sequences

| Sequence | Touches | Duration | Trigger |
|----------|---------|----------|---------|
| Cold Email | 3 | 7-10 days | New Lead → Contacted |
| Non-Booker | 4 | 12 days | Engaged 72+ hours |
| No-Show | 3 | 48 hours | Missed call |
| Verbal Commit | 3 | 3 days | Call done, pending payment |
| Think About It | 3 | 7 days | Call done, considering |
| Ghost | 2 | 10 days | Call done, then silent |

---

## 💰 Monthly Costs

### Current (You're Already Paying)
- Instantly: $200/mo
- Email accounts (50): $250/mo
- **Subtotal:** $450/mo

### New Infrastructure
- Claude API (Opus 5.5, claude-opus-5-5): $150-300/mo (volume-dependent)
- Modal (webhooks): $0-20/mo (free tier likely sufficient)
- Python hosting: $5-25/mo (optional, for monitoring)
- **New Total:** $155-345/mo

**Total Operating Cost:** ~$605-795/mo

---

## 🔐 Security & Credentials

All sensitive data stored in `.env` (gitignored):
- ✅ Instantly API key
- ✅ Claude API key
- ✅ Google Sheets credentials
- ✅ Calendar API credentials
- ✅ Slack webhook (optional)

**Never commit:**
- `.env`
- `credentials.json`
- `token.json`
- `.tmp/` folder

---

## 📚 Documentation

- **[INDEX.md](INDEX.md)** - Main control center (start here daily)
- **[QUICK_START.md](QUICK_START.md)** - Setup instructions
- **[Master SOP](../Downloads/Advero Solutions Master SOP v2.docx)** - Business processes
- **[Claude.md](Agentic Worklfows/Claude.md)** - Architecture principles
- **Directive files** - Specific operation instructions

---

## 🛠️ Development

### Local Setup
```bash
# Clone repo
cd /Users/lorenzovillarreal/Desktop/AdveroSolutions

# Install dependencies
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env with your API keys

# Initialize CRM
python execution/initialize_crm.py

# Test system
python execution/test_system.py
```

### Deploy Cloud Automation
```bash
# Login to Modal
modal token new

# Deploy webhooks
modal deploy execution/modal_webhook.py

# Verify deployment
curl https://[your-modal-url]/status
```

---

## 🧪 Testing

```bash
# Test CRM connection
python execution/google_sheets_crm.py

# Test full system
python execution/test_system.py

# Test specific component
python -m pytest execution/test_instantly.py
```

---

## 🔄 Self-Healing

System automatically fixes common issues:

1. **API rate limits** → Backs off and retries
2. **Invalid stage transitions** → Logs error, doesn't break system
3. **Missing data** → Uses defaults, flags for review
4. **Webhook failures** → Retries with exponential backoff
5. **Sheet access errors** → Refreshes auth token

All learnings update directives automatically.

---

## 📊 Monitoring

### Daily
- Check [Campaign Stats](directives/USER/check_campaign_stats.md)
- Review `.tmp/error_log.txt`

### Weekly
- Review Modal webhook logs
- Check email deliverability
- Validate stage distributions

### Monthly
- Analyze conversion metrics
- Update email templates if needed
- Review and refine sequences

---

## 🚨 Troubleshooting

| Issue | Solution |
|-------|----------|
| Replies not answered | Check Modal webhook status |
| Sequences not sending | Verify Instantly API connection |
| CRM not updating | Re-auth Google Sheets credentials |
| No-shows not detected | Check calendar integration |

Full troubleshooting: [QUICK_START.md](QUICK_START.md#troubleshooting)

---

## 📞 Support

1. Check [INDEX.md](INDEX.md) for quick reference
2. Review relevant directive in `directives/USER/`
3. Check `.tmp/error_log.txt`
4. Run `python execution/test_system.py`

---

## 🎯 Next Steps

1. ✅ Complete setup (follow [QUICK_START.md](QUICK_START.md))
2. 📥 Import first batch of leads
3. 🚀 Launch first campaign
4. 📊 Monitor for 24 hours
5. 🔧 Refine based on metrics
6. 📈 Scale to full volume (2000 emails/day)

---

**Built with the 3-layer architecture:** Directives (what) → Orchestration (decisions) → Execution (work)

**Status:** 🟢 Operational | **Version:** 1.0 | **Last Updated:** January 2026
