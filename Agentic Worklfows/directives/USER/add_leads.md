# Add Leads to CRM

**Purpose:** Import new leads into the AdveroSolutions CRM
**When to use:** You have a new list of prospects to add to the system
**Frequency:** As needed (typically daily or weekly)

---

## What This Does

1. Validates lead data (required fields, email format)
2. Generates unique lead IDs
3. Adds leads to Master_Leads sheet
4. Sets initial stage to "New Lead"
5. Records creation timestamp
6. Returns summary of import results

---

## Required Tools

- `execution/google_sheets_crm.py` - CRM operations

---

## Input Format

You can provide leads in any of these formats:

### Option 1: CSV/Excel Data
Paste data with these columns (minimum required):
```
first_name, last_name, email, company_name, industry
```

Optional columns:
```
phone, website, city, state, source, notes
```

### Option 2: JSON Format
```json
[
  {
    "first_name": "John",
    "last_name": "Smith",
    "email": "john@hvacpros.com",
    "company_name": "HVAC Pros LLC",
    "industry": "HVAC",
    "phone": "555-1234",
    "website": "hvacpros.com",
    "city": "Dallas",
    "state": "TX",
    "source": "Scraped - Google Maps",
    "notes": "Family-owned, 25+ years"
  }
]
```

### Option 3: Plain Text
Just tell me the details:
```
"Add a lead: John Smith at HVAC Pros LLC, email is john@hvacpros.com, HVAC industry, Dallas TX"
```

---

## Validation Rules

**Required fields:**
- `first_name` - Cannot be empty
- `last_name` - Cannot be empty
- `email` - Must be valid email format
- `company_name` - Cannot be empty
- `industry` - Must be one of: HVAC, Roofing, Plumbing, Electrical

**Optional fields:**
- `phone` - Any format accepted
- `website` - URL or domain name
- `city` - City name
- `state` - 2-letter state code preferred
- `source` - Where lead came from (default: "Manual Import")
- `notes` - Any additional context

---

## Process

When you trigger this directive:

1. **I parse your input** into structured lead data
2. **Validate all required fields** are present and formatted correctly
3. **Check for duplicates** in CRM (by email)
4. **Generate unique lead IDs** for new leads
5. **Add to Master_Leads sheet** with stage = "New Lead"
6. **Return summary:**
   - Number of leads added
   - Number of duplicates skipped
   - Any errors encountered

---

## Output

You'll receive a summary like:
```
✅ Import Complete

📊 Results:
   - Successfully added: 47 leads
   - Duplicates skipped: 3 leads
   - Errors: 0

📥 New leads are in stage: "New Lead"

🚀 Next step: Run start_cold_campaign.md to launch outreach
```

---

## Next Actions

After adding leads, you typically want to:

1. **[Start Cold Campaign](start_cold_campaign.md)** - Launch the 3-email sequence
2. **[Check Campaign Stats](check_campaign_stats.md)** - Verify import successful

---

## Edge Cases

### Duplicate Emails
- System checks for existing email in CRM
- Duplicates are skipped (not added)
- You'll see summary of how many skipped

### Invalid Email Format
- Leads with invalid emails are rejected
- Error message shows which emails failed validation
- Fix and re-import those leads

### Missing Required Fields
- Import will fail for leads missing required fields
- Error message shows which fields are missing
- Add missing data and re-import

### Multiple Industries
- If company does multiple services (e.g., HVAC + Plumbing), choose primary
- Add note about secondary services in `notes` field

---

## Example Usage

### Single Lead
```
"Add this lead:
John Smith
john@hvacpros.com
HVAC Pros LLC
HVAC industry
Dallas, TX
Found on Google Maps"
```

### Bulk Import from CSV
```
"I have a CSV with 200 leads. Here's the data:
[paste CSV content]
Import all of these."
```

### From Scraped Data
```
"Import these leads from my Apollo export:
[paste data]
Mark source as 'Apollo - HVAC Dallas'"
```

---

## Common Questions

**Q: How many leads can I import at once?**
A: No hard limit, but batches of 100-500 work best. For larger lists, break into multiple imports.

**Q: Can I import leads from different industries together?**
A: Yes, as long as each lead has correct industry specified.

**Q: What if I accidentally import the same list twice?**
A: System checks for duplicate emails and skips them automatically.

**Q: Can I update existing leads with this?**
A: No, this only adds NEW leads. To update existing leads, use `fix_lead_stage.md` or edit the sheet directly.

---

## Error Handling

If import fails:
1. Check error message in output
2. Verify data format matches requirements
3. Ensure Google Sheets CRM is accessible
4. Check `.tmp/error_log.txt` for details
5. Fix issues and retry

Common errors:
- "GOOGLE_SHEET_ID not found" → Update .env file
- "credentials.json not found" → Add Google credentials
- "Invalid email format" → Fix email addresses
- "Missing required field" → Add missing data

---

**Ready to import leads? Paste your data below or tell me what you need.**
