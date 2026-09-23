#!/usr/bin/env python3
"""
Part B - Email export -> Instantly-ready CSV  (med spa cold-email lead gen)

Takes an email-finder export (Anymail Finder or Hunter) and writes the
Instantly upload CSV.

Anymail Finder exports already carry the business data (company, city, reviews,
domain, Google link) PLUS the decision-maker's real name and verified email, so
this is normally a ONE-FILE step. If you instead give it a bare Hunter list
that's just emails, it falls back to merging company/city/etc. from the Part A
output (`..._cleaned_for_hunter.csv`) by domain.

What it does:
1. Keeps only valid, personal emails (drops invalid ones and role inboxes
   like info@/sales@/support@).
2. Uses the real first name from the finder (person_first_name) when present;
   otherwise the Part A name; otherwise "there".
3. De-duplicates emails.
4. Writes: firstName, email, companyName, city, reviewCount, website,
   googleMapsUrl

Run:   python part_b.py
Standard library only. No external API calls.
"""

import csv
import os
import re
import sys

# Role-based / generic local parts to drop. Matched as WHOLE WORDS (the local
# part is split on non-letters), so real names that merely contain a role word
# are safe - e.g. "shumaila" (has "mail"), "fronteras" (has "front").
ROLE_WORDS = frozenset((
    "info", "contact", "hello", "team", "admin", "support", "office",
    "help", "sales", "mail", "service", "inquiry", "enquiry", "general",
    "billing", "accounts", "reception", "front", "booking", "quote",
    "quotes", "estimate", "estimates", "request", "requests", "noreply",
    "reply", "hr", "careers", "jobs", "marketing", "hello",
))


def base_domain(value):
    """Strip a URL/host to its base domain ('' if none)."""
    d = (value or "").strip().lower()
    if not d:
        return ""
    d = d.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if d.startswith("www."):
        d = d[4:]
    return d.split(":", 1)[0]


def find_col(fieldnames, exacts=(), contains=(), exclude=()):
    """Find a column by exact (case-insensitive) name, then by substring."""
    low = {c.lower(): c for c in fieldnames if c}
    for e in exacts:
        if e in low:
            return low[e]
    for c in fieldnames:
        cl = (c or "").lower()
        if cl and any(k in cl for k in contains) \
                and not any(x in cl for x in exclude):
            return c
    return None


def process_email_export(export_path, part_a_path=None):
    """Reshape an Anymail/Hunter export into the Instantly upload CSV."""
    folder = os.path.dirname(os.path.abspath(export_path))
    stem = os.path.splitext(os.path.basename(export_path))[0]
    output_path = os.path.join(folder, stem + "_instantly_ready.csv")

    with open(export_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = list(reader)

    # ---- Resolve columns (works for Anymail Finder and Hunter layouts) ----
    email_col = find_col(fields, exacts=("valid_email_only", "email",
                                         "email address", "work email"),
                         contains=("email",),
                         exclude=("type", "status", "verif"))
    first_col = find_col(fields, exacts=("person_first_name", "first name",
                                         "first_name"))
    person_col = find_col(fields, exacts=("person_name", "full name",
                                          "full_name"))
    parta_first = find_col(fields, exacts=("firstname",))
    company_col = find_col(fields, exacts=("companyname", "company", "title",
                                           "organization", "organisation"))
    city_col = find_col(fields, exacts=("city",))
    review_col = find_col(fields, exacts=("reviewcount",), contains=("review",))
    domain_col = find_col(fields, exacts=("domain", "website", "website url"),
                          contains=("domain", "website"))
    maps_col = find_col(fields, exacts=("googlemapsurl", "placeurl",
                                        "google maps url"),
                        contains=("maps", "placeurl"))
    etype_col = find_col(fields, exacts=("email_type",))
    status_col = find_col(fields, exacts=("amf_status",))

    if email_col is None:
        raise ValueError("No email column found. Headers: "
                         + (", ".join(fields) or "(none)"))

    # Self-contained if the export already carries the business fields.
    self_contained = company_col is not None
    a_by_domain = {}
    if not self_contained:
        if not part_a_path:
            raise ValueError("This export has no company column, so I need the "
                             "Part A output too. Re-run and provide it.")
        with open(part_a_path, "r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                dom = base_domain(r.get("domain", ""))
                if dom and dom not in a_by_domain:
                    a_by_domain[dom] = {
                        "firstName": (r.get("firstName") or "").strip(),
                        "companyName": (r.get("companyName") or "").strip(),
                        "city": (r.get("city") or "").strip(),
                        "reviewCount": (r.get("reviewCount") or "").strip(),
                        "googleMapsUrl": (r.get("googleMapsUrl") or "").strip(),
                    }

    total_in = len(rows)
    removed = {"invalid_email": 0, "role_email": 0, "duplicate": 0}
    seen = set()
    out_rows = []
    real_names = 0

    for row in rows:
        email = (row.get(email_col, "") or "").strip().lower()
        if not email or "@" not in email:
            removed["invalid_email"] += 1
            continue
        # Honor the finder's own validity flags when present.
        if etype_col and (row.get(etype_col, "") or "").strip().lower() \
                not in ("", "valid"):
            removed["invalid_email"] += 1
            continue
        if status_col and (row.get(status_col, "") or "").strip().lower() \
                not in ("", "ok"):
            removed["invalid_email"] += 1
            continue

        local = email.split("@", 1)[0]
        tokens = [t for t in re.split(r"[^a-z]+", local.lower()) if t]
        if any(t in ROLE_WORDS for t in tokens):
            removed["role_email"] += 1
            continue
        if email in seen:
            removed["duplicate"] += 1
            continue
        seen.add(email)

        dom = base_domain(email.split("@", 1)[1])
        if domain_col:
            dom = base_domain(row.get(domain_col, "")) or dom
        merged = a_by_domain.get(dom, {}) if not self_contained else {}

        # First name: prefer the finder's real person name.
        first = ""
        if first_col:
            first = (row.get(first_col, "") or "").strip()
        if not first and person_col:
            pn = (row.get(person_col, "") or "").strip()
            first = pn.split()[0] if pn else ""
        if not first and parta_first:
            v = (row.get(parta_first, "") or "").strip()
            first = v if v and v.lower() != "there" else ""
        if not first:
            first = merged.get("firstName", "")
        if not first or first.lower() == "there":
            first = "there"
        else:
            real_names += 1

        def field(col, key):
            if col:
                v = (row.get(col, "") or "").strip()
                if v:
                    return v
            return merged.get(key, "")

        out_rows.append({
            "firstName": first,
            "email": email,
            "companyName": field(company_col, "companyName"),
            "city": field(city_col, "city"),
            "reviewCount": field(review_col, "reviewCount"),
            "website": dom,
            "googleMapsUrl": field(maps_col, "googleMapsUrl"),
        })

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "firstName", "email", "companyName", "city", "reviewCount",
            "website", "googleMapsUrl"])
        writer.writeheader()
        writer.writerows(out_rows)

    print("=" * 56)
    print("PART B - EMAIL EXPORT -> INSTANTLY CSV - SUMMARY")
    print("=" * 56)
    print("Mode:                          {}".format(
        "self-contained (one file)" if self_contained
        else "merged with Part A output"))
    print("Email column used:             {}".format(email_col))
    print("First-name column used:        {}".format(
        first_col or person_col or parta_first or "(none -> 'there')"))
    print("-" * 56)
    print("Rows in:                       {}".format(total_in))
    print("Removed - invalid email:       {}".format(removed["invalid_email"]))
    print("Removed - role/generic email:  {}".format(removed["role_email"]))
    print("Removed - duplicate email:     {}".format(removed["duplicate"]))
    print("Rows out:                      {}".format(len(out_rows)))
    print("  with a real first name:      {}".format(real_names))
    print("  defaulted to 'there':        {}".format(len(out_rows) - real_names))
    print("Output file:                   {}".format(output_path))
    print("=" * 56)
    return output_path


if __name__ == "__main__":
    print("Part B - email export -> Instantly CSV\n")

    def ask(label):
        for _ in range(3):
            raw = input(label).strip()
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
                raw = raw[1:-1]
            raw = raw.strip().replace("\\ ", " ")
            if os.path.isfile(raw):
                return raw
            print("  File not found: {!r} - try again.\n".format(raw))
        return ""

    export = ask("Path to the email-finder export (Anymail/Hunter) CSV: ")
    if not export:
        print("No valid file provided. Exiting.")
        sys.exit(1)

    # Peek at the headers: only ask for the Part A file if we actually need it.
    with open(export, "r", encoding="utf-8-sig", newline="") as fh:
        head = csv.DictReader(fh).fieldnames or []
    need_part_a = find_col(head, exacts=("companyname", "company", "title",
                                         "organization", "organisation")) is None
    part_a = ""
    if need_part_a:
        print("\nThis export doesn't carry the company data, so I also need")
        print("the Part A output to merge it in.")
        part_a = ask("Path to the Part A output (..._cleaned_for_hunter.csv): ")
        if not part_a:
            print("Missing the Part A file. Exiting.")
            sys.exit(1)

    try:
        process_email_export(export, part_a or None)
    except Exception as e:
        print("\nERROR: {}".format(e))
        sys.exit(1)
