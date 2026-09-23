# Separate Contacted Leads from Fresh Leads

## Overview
Checks your Instantly campaigns to identify leads that have already been contacted, then separates them from new CSV leads. This allows you to prioritize fresh leads with your new offer while scheduling previously contacted leads for re-engagement after a cooling-off period.

## When to Use
- Before launching a new campaign with a different offer
- When you have a mixed list of leads and want to avoid immediately re-contacting recent leads
- To implement proper cooling-off periods between contact attempts
- When rotating offers to your lead database

## Inputs Required
1. **CSV file with leads** - Your lead list with email addresses
   - Must contain an email column (common names: email, Email, EMAIL, email_address)
   - Can include any other lead data fields

2. **Minimum weeks delay** (optional, default: 2 weeks)
   - How long to wait before re-contacting previously contacted leads

## Process Flow
1. Connect to Instantly API and fetch all campaigns
2. For each campaign, get all leads and their contact history
3. Build a list of all contacted email addresses with details:
   - Which campaigns they were in
   - How many emails sent/opened/replied
   - Last contact date
4. Read your input CSV file
5. Compare each lead against the contacted list
6. Separate into two groups:
   - **Fresh leads**: Never contacted, ready for immediate outreach
   - **Previously contacted**: Need cooling-off period before re-engagement
7. Calculate reintroduction dates based on last contact + minimum weeks
8. Save three output files with timestamp

## Outputs
1. **fresh_leads_[timestamp].csv** - Ready for immediate campaign
   - All leads that have never been contacted
   - Original data preserved

2. **previously_contacted_[timestamp].csv** - For delayed re-engagement
   - Leads that have been contacted before
   - Includes contact_history field with campaign details
   - Includes reintroduction_date (when they can be contacted again)
   - Includes days_until_ready counter

3. **lead_separation_summary_[timestamp].txt** - Summary report
   - Total counts for each category
   - Reintroduction schedule breakdown

## Tools to Use
```bash
# Test connection first
python execution/test_instantly_connection.py

# Run the separation
python execution/separate_contacted_leads.py path/to/your_leads.csv

# With custom delay period (e.g., 3 weeks)
python execution/separate_contacted_leads.py path/to/your_leads.csv --min-weeks 3

# Save outputs to specific directory
python execution/separate_contacted_leads.py path/to/your_leads.csv --output-dir ./separated_leads/
```

## Edge Cases & Handling
- **No email column**: Script will try common variations (email, Email, EMAIL, etc.)
- **API rate limits**: Script handles pagination automatically
- **Large campaigns**: Processes in batches of 100 leads
- **Missing contact dates**: Uses current date + minimum weeks for scheduling
- **Duplicate emails**: Consolidated into single entry with combined history

## Example Workflow
1. Export your new lead list to CSV
2. Run the separation script:
   ```bash
   python execution/separate_contacted_leads.py new_leads.csv --min-weeks 2
   ```
3. Upload `fresh_leads_[timestamp].csv` to your new campaign immediately
4. Schedule `previously_contacted_[timestamp].csv` for later:
   - Check the reintroduction_date column
   - Upload batches as they become ready
   - Or set calendar reminder to upload after cooling period

## Reintroduction Strategy
The script adds these fields to help manage reintroduction:
- **reintroduction_date**: Exact date when lead can be contacted
- **days_until_ready**: Countdown to help with scheduling
- **contact_history**: JSON with full engagement history

You can:
1. Sort by reintroduction_date to create weekly batches
2. Filter for days_until_ready <= 0 to find ready leads
3. Review contact_history to personalize re-engagement

## Best Practices
- Run this before every new campaign to avoid oversaturating leads
- Use 2-3 week minimum cooling periods for cold outreach
- Consider longer delays (4-6 weeks) for leads that never responded
- Keep the summary reports for campaign planning
- For leads that replied, consider manual review before re-engagement