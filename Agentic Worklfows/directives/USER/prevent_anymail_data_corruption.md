# Prevent AnyMailFinder Data Corruption

**Problem:** When you export leads to CSV, upload to AnyMailFinder, and paste results back to Google Sheets, the rows can misalign causing wrong email→company assignments.

**Result:** One person's email gets assigned to 100+ different companies (data corruption).

---

## ❌ What NOT To Do

**Don't:**
1. Export entire sheet to CSV
2. Upload to AnyMailFinder
3. Download results
4. **Copy-paste results directly back to Google Sheets**

**Why this fails:** If AnyMailFinder reorders rows, skips rows, or you paste with an offset, emails get assigned to the wrong companies.

---

## ✅ Correct Process

### Method 1: Use a Merge Key (Phone Number)

1. **Export with unique identifier**
   - Include a column that won't change (phone number, row ID, etc.)
   - Export: `phone, website, company_name`

2. **Upload to AnyMailFinder**
   - Map columns properly
   - Download results (now has: `phone, website, company_name, email, person_name`)

3. **Merge back using phone as key**
   ```python
   # Use VLOOKUP in Google Sheets or a merge script
   # Match by phone number, not by row position
   ```

4. **Verify before committing**
   - Spot-check 10-20 rows
   - Make sure phone + email + company match correctly

### Method 2: Small Batches with Manual Verification

1. **Work in batches of 100-500 rows**
   - Export rows 1-100
   - Upload to AnyMailFinder
   - Download results
   - Paste back and **manually verify** 5-10 rows
   - If correct, move to next batch

2. **Why this works:** Smaller batches are easier to verify, and if something goes wrong, you only corrupt 100 rows instead of 20,000

### Method 3: Use the Automated Script (Recommended)

Use the provided `clean_corrupted_lead_data.py` script:

1. **Export clean data**:
   ```bash
   python execution/clean_corrupted_lead_data.py --export-clean-csv
   ```

2. **Upload CSV to AnyMailFinder**
   - Use the exported CSV (already deduplicated)

3. **Download results from AnyMailFinder**

4. **Use a merge script** (not copy-paste):
   ```python
   # Script should:
   # 1. Read AnyMailFinder results CSV
   # 2. Read Google Sheet
   # 3. Match by phone number
   # 4. Update only the email/name columns for matching rows
   ```

---

## 🛡️ Prevention Checklist

Before uploading to AnyMailFinder:

- [ ] Data is **deduplicated** (no duplicate phone numbers)
- [ ] Export includes a **unique identifier** (phone, row ID, etc.)
- [ ] You have a **backup** of the original sheet
- [ ] You plan to **merge by key**, not paste by position

After downloading from AnyMailFinder:

- [ ] **Don't immediately paste** into Google Sheets
- [ ] **Verify row count** matches (input rows = output rows)
- [ ] **Spot-check 10 rows** - does phone match email?
- [ ] Use **VLOOKUP or merge script** to match by phone

---

## 🔧 Fixing Existing Corruption

If you've already corrupted the data:

1. **Analyze the damage**:
   ```bash
   python execution/clean_corrupted_lead_data.py --analyze
   ```

2. **Clean the data** (removes duplicates + clears corrupt emails):
   ```bash
   python execution/clean_corrupted_lead_data.py --clean
   ```

3. **Export clean CSV**:
   ```bash
   python execution/clean_corrupted_lead_data.py --export-clean-csv
   ```

4. **Re-upload to AnyMailFinder** and merge properly this time

---

## 📊 Data Quality Checks

After any bulk operation, run these checks:

1. **Duplicate email check**:
   ```
   =COUNTIF($E$2:$E, E2)
   ```
   If any cell shows > 1, you have duplicates

2. **Email domain vs website domain match**:
   - Email: `john@acmecompany.com`
   - Website: `acmecompany.com`
   - Should match (or be close)

3. **Spot-check suspicious emails**:
   - CEO emails from Fortune 500 companies (e.g., `sundar@google.com`)
   - Same email appearing for competitor companies
   - Email domains that don't match website domains

---

## 🚨 Red Flags

Stop and investigate if you see:

- Same email appearing for 10+ different companies
- Fortune 500 CEO emails (Sundar Pichai, etc.) for small local businesses
- Email domain doesn't match company website
- Row count changed after upload/download from AnyMailFinder

---

## Summary

**Golden Rule:** Never trust copy-paste for bulk data operations. Always merge by a unique key (phone number) and verify before committing.
