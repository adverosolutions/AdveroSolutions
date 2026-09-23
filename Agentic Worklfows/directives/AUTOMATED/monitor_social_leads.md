# Monitor Social Media Leads (AUTOMATED)

**Purpose:** Real-time browser monitoring for lawn care service requests on Facebook Groups and Nextdoor
**Type:** Browser Extension (Tampermonkey/Chrome Extension)
**Cost:** $0 (100% free)
**Frequency:** Continuous monitoring while browsing

---

## What This Does

The Social Lead Monitor:
1. Runs as a browser extension while you browse Facebook Groups and Nextdoor
2. Watches for lawn care keywords in posts as they appear on screen
3. Classifies posts using AI to identify genuine leads
4. Sends instant push notifications to your phone via ntfy.sh (free)
5. Logs qualified leads to Google Sheets CRM
6. Highlights relevant posts on the page for easy spotting

**Key Advantage:** Not scraping - you're a legitimate logged-in user browsing normally. Extension just watches the content that's already loaded in your browser. Zero risk of bans or CAPTCHAs.

---

## Architecture

### Browser Extension Components

1. **Content Script** (`content-script.js`)
   - Runs on Facebook Groups and Nextdoor pages
   - Observes DOM for new posts (MutationObserver)
   - Searches for lawn care keywords
   - Highlights matching posts with yellow border
   - Extracts post data: author, text, timestamp, URL

2. **Background Script** (`background.js`)
   - Receives detected posts from content script
   - Calls AI classification API
   - Sends ntfy.sh notifications for qualified leads
   - Logs to Google Sheets CRM
   - Manages settings and deduplication

3. **Popup UI** (`popup.html`)
   - Enable/disable monitoring
   - View recent detections
   - Configure keywords and notification threshold
   - Test notifications

---

## How It Works

### Real-Time Detection Flow

```
User browses Facebook Group
  → Content script watches DOM for new posts
  → Regex searches for lawn care keywords
  → Match found → highlight post + extract data
  → Send to background script
  → Check deduplication cache (seen this post?)
    → Already seen: skip
    → New post: continue ↓
  → Call AI classification API
  → Confidence > 70%?
    → YES: Send ntfy.sh notification + log to Sheets
    → NO: Skip notification (just log for analysis)
  → User's phone buzzes instantly
  → User clicks notification → opens to exact post
  → User responds manually
```

---

## Installation

### Method 1: Tampermonkey (Easiest)

1. Install Tampermonkey extension (Chrome/Firefox/Edge)
2. Create new script from `execution/tampermonkey-social-monitor.js`
3. Configure ntfy topic in script settings
4. Browse Facebook Groups - script auto-activates

### Method 2: Chrome Extension (More Features)

1. Load unpacked extension from `chrome-extension/` folder
2. Configure settings in extension popup
3. Grant permissions for Facebook and Nextdoor
4. Extension runs automatically on target sites

---

## Configuration

### Required Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `NTFY_TOPIC` | Your private ntfy.sh topic name | (user sets) |
| `OPENAI_API_KEY` | For AI classification | (from .env) |
| `GOOGLE_SHEET_ID` | CRM sheet for logging | (from .env) |
| `CONFIDENCE_THRESHOLD` | Minimum confidence to notify (0-100) | 70 |

### Keywords (Configurable)

Default lawn care keywords:
- `lawn`, `mowing`, `landscaping`, `yard work`, `grass cutting`
- `lawn service`, `lawn care`, `landscaping service`
- `need.*mow`, `looking for.*landscap`, `recommend.*lawn`

Regex patterns catch variations like:
- "Need someone to mow my lawn"
- "Looking for landscaping recommendations"
- "Anyone do yard work?"

---

## Notification Format

### Phone Notification (ntfy.sh)

```
🌿 LAWN LEAD: Phoenix, AZ

"Need someone to mow my lawn weekly.
Small yard, easy access..."

Platform: Facebook - Home Services Group
Confidence: 85%
Posted: 5 minutes ago

[Click to open post]
```

**Notification Levels:**
- 🔥 **Urgent** (confidence > 90%): High priority sound
- 🌿 **Normal** (confidence 70-90%): Default notification
- 📋 **Low** (confidence 50-70%): Silent log only (no notification)

---

## Data Logged to Google Sheets

New tab: **Social Leads**

| Column | Description |
|--------|-------------|
| `timestamp` | When detected |
| `platform` | facebook / nextdoor |
| `group_name` | Group or neighborhood name |
| `author` | Post author name |
| `post_text` | Full post content |
| `post_url` | Direct link to post |
| `detected_keywords` | Which keywords matched |
| `ai_classification` | genuine_lead / spam / chatter |
| `confidence_score` | 0-100 |
| `urgency` | high / medium / low |
| `services_needed` | Extracted from post |
| `location` | Extracted city/area |
| `status` | new / contacted / closed |

---

## AI Classification

### Prompt Template

```
Analyze this social media post and determine if it's a genuine lead for lawn care services.

Post: "{post_text}"
Platform: {platform}
Group: {group_name}

Classify as:
- genuine_lead: Person actively looking for lawn care service
- info_request: Asking for recommendations or information
- spam: Advertisement or irrelevant
- chatter: General discussion, not seeking service

Extract:
- urgency: high (ASAP, urgent, today) / medium (this week) / low (no timeline)
- services_needed: mowing, landscaping, cleanup, etc.
- location: city or neighborhood mentioned
- confidence: 0-100 (how certain this is a real lead)

Return JSON.
```

### Classification Examples

**Genuine Lead (notify):**
- "Need someone to mow my lawn weekly starting next week"
- "Looking for affordable landscaping service in Scottsdale"
- "My lawn guy quit, need someone reliable ASAP"

**Info Request (notify if confidence high):**
- "Can anyone recommend a good lawn service?"
- "How much does weekly mowing usually cost?"

**Spam (don't notify):**
- "🔥 BEST LAWN SERVICE IN TOWN - CALL NOW 📞"
- "I offer professional landscaping, DM for quote"

**Chatter (don't notify):**
- "My lawn looks terrible this year"
- "Love how green everyone's yards look"

---

## Deduplication

### Local Storage Cache

Extension maintains a cache of seen post URLs in browser storage:
- Key: Post URL hash
- Expiry: 30 days
- Before processing: Check if URL already seen
- Prevents duplicate notifications for same post

---

## Platforms Supported

### Facebook Groups ✅
- Detects posts in group feeds
- Works on: `/groups/{groupId}`
- Extracts: Author, post text, timestamp, post ID
- Limitation: Only sees posts you scroll to (not retroactive)

### Nextdoor ✅
- Detects neighborhood posts
- Works on: Main feed and category pages
- Extracts: Author, post text, location, post URL
- Limitation: Requires being logged in

### Future Platforms (Easy to Add)
- Craigslist Services section
- Reddit local subreddits
- Yelp request-a-quote pages

---

## Usage Modes

### Mode 1: Passive Helper (Recommended)

You browse groups naturally when you have time:
- Morning coffee: Check 3-5 groups
- Lunch break: Quick scroll
- Evening: Catch up on new posts

Extension highlights relevant posts as you scroll. Notifications only for high-confidence leads.

**Time investment:** 15-30 min/day browsing
**Expected leads:** 3-8 per week

---

### Mode 2: Active Monitor (24/7)

Keep browser tab open with auto-refresh:
- Open 5-10 target groups in pinned tabs
- Auto-refresh every 10 minutes
- Extension monitors in background
- Close laptop lid / leave running

**Time investment:** 5 min setup, runs automatically
**Expected leads:** 10-20 per week

---

### Mode 3: Hybrid

Passive browsing + background monitoring on spare device:
- Primary: Browse on phone/laptop naturally
- Secondary: Old laptop monitors 24/7

**Best of both worlds**

---

## Troubleshooting

### "Notifications not working"

1. Check ntfy app is installed and topic is correct
2. Test notification: `curl -d "test" ntfy.sh/{your-topic}`
3. Verify extension has permission to make HTTP requests
4. Check browser console for errors

### "Not detecting posts"

1. Verify you're on a supported page (Facebook Group, Nextdoor)
2. Check keyword settings - may need to add more terms
3. Try refreshing the page
4. Check browser console for selector errors

### "Too many false positives"

1. Increase confidence threshold (70 → 80)
2. Refine keywords (remove generic terms)
3. Add negative keywords (filter out "offering" / "I do")

### "Extension not loading"

1. Check manifest.json permissions
2. Reload extension in chrome://extensions
3. Check for JavaScript errors in background page console

---

## Performance

### Resource Usage

- **CPU:** Minimal (only when new posts appear)
- **Memory:** ~10-20 MB per monitored tab
- **Network:** ~1-2 KB per classification API call
- **Battery:** Negligible impact on laptop

### API Costs

- **OpenAI classification:** ~$0.001 per post
- **ntfy.sh:** $0 (unlimited)
- **Google Sheets API:** $0 (free tier)

**Expected monthly cost:** $1-3 for AI (if 1000-3000 posts/month)

---

## Privacy & Security

### What the extension accesses:

- ✅ Post content (text only, already visible to you)
- ✅ Author names (public info)
- ✅ Post URLs (for linking)
- ❌ Does NOT access: messages, friend lists, photos, personal data

### Data storage:

- Local cache: Stored in browser only
- API calls: OpenAI (classification), Google Sheets (logging)
- Notifications: ntfy.sh (no account, no tracking)

### Compliance:

- Read-only monitoring (no posting, no automation)
- You manually respond to leads (human interaction)
- Personal use (not commercial data scraping)
- Respects platform terms: You're a real user browsing normally

---

## Next Steps After Detection

When you get a notification:

1. **Click notification** → Opens directly to post
2. **Read full context** → Check if still relevant
3. **Respond manually** → Comment or DM naturally
4. **Update CRM** → Mark as "contacted" in Google Sheet
5. **Track outcome** → Won/lost/no response

**Keep it human.** The system finds leads, but you build relationships.

---

## Future Enhancements

### Planned Features

- [ ] Sentiment analysis (urgent vs casual tone)
- [ ] Photo detection (lawn photos = more serious)
- [ ] Response rate tracking (which groups convert best)
- [ ] Auto-reply suggestions (pre-written templates)
- [ ] Integration with booking calendar
- [ ] Multi-user support (team notifications)

### Alternative Notification Methods

If ntfy.sh doesn't work for you:
- Pushover ($5 one-time)
- Slack DM
- Email-to-SMS (via carrier gateway)
- Discord webhook

---

## Tools Required

- `execution/ai_api.py` - AI classification (existing)
- `execution/google_sheets_client.py` - CRM logging (existing)
- `chrome-extension/manifest.json` - Extension config (new)
- `chrome-extension/content-script.js` - DOM monitoring (new)
- `chrome-extension/background.js` - API orchestration (new)
- `chrome-extension/popup.html` - Settings UI (new)

---

## Learnings

*(Will be updated as we build and deploy)*

### Initial Build Notes

- Browser extension approach chosen over scraping for reliability
- ntfy.sh selected for zero-cost notifications
- AI classification prevents false positive spam
- Local deduplication cache prevents duplicate notifications
- Works on any website (Facebook, Nextdoor, Craigslist, etc.)

---

## Summary

This system turns your normal social media browsing into an automated lead generation machine. You browse groups like you normally would, and the extension watches for opportunities in real-time. When someone posts "need lawn service", your phone buzzes instantly. You respond while the lead is hot.

**Zero scraping. Zero risk. Zero cost.**
