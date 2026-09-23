#!/usr/bin/env python3
"""Rebuild source_cleaning_50.json from recorded scraper output.

The fixture is 50 real businesses from
``Coding/lead-scrape-2026/output/production/cleaning__b*.json`` (the Sept 1
sharded Apify run) with the verified email REMOVED, so the pipeline has to earn
the address the way a Google Maps row would, plus 8 handwritten negatives that
pin the misses that actually happened: the snow-removal company mailed as a
cleaner, a residential maid service, a restoration franchise, a janitorial
supply shop.

Two of the real rows keep a domain that is already in the live workspace, so
the suppression stage has something to catch in the rehearsal.

    python3 services/list_factory/fixtures/build_fixture.py
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))  # Agentic Worklfows
ROOT = os.path.dirname(BASE)                                     # AdveroSolutions
PROD = os.path.join(ROOT, "Coding", "lead-scrape-2026", "output", "production")

KEEP = (
    "company_name", "company_website", "city", "state", "country", "industry",
    "keywords", "company_description", "company_size", "company_phone",
    "first_name", "last_name", "job_title", "headline",
)

# The misses that made this rubric necessary. Written by hand because the
# recorded Apify run was already filtered and does not contain them; the live
# Google Maps source does.
NEGATIVES = [
    {
        "company_name": "Northland Snow Removal and Lawn",
        "company_website": "https://northlandsnowandlawn.example",
        "city": "Minneapolis", "state": "Minnesota", "country": "United States",
        "industry": "Facilities Services",
        "keywords": "snow removal, snow plowing, salting, lawn care, spring cleanup",
        "company_description": "Commercial snow removal and lawn maintenance for property managers.",
        "company_size": 12, "first_name": "Dale", "last_name": "Hovland", "job_title": "Owner",
    },
    {
        "company_name": "Tidy Nest Maid Service",
        "company_website": "https://tidynestmaids.example",
        "city": "Austin", "state": "Texas", "country": "United States",
        "industry": "Consumer Services",
        "keywords": "maid service, house cleaning, residential cleaning, move out cleaning",
        "company_description": "Weekly and biweekly house cleaning for busy families.",
        "company_size": 9, "first_name": "Brenda", "last_name": "Alvarez", "job_title": "Owner",
    },
    {
        "company_name": "ServiceMaster Restore of Akron",
        "company_website": "https://svmakron.example",
        "city": "Akron", "state": "Ohio", "country": "United States",
        "industry": "Facilities Services",
        "keywords": "water damage, fire damage, mold remediation, disaster recovery, restoration",
        "company_description": "24/7 water and fire damage restoration. A ServiceMaster franchise.",
        "company_size": 30, "first_name": "Greg", "last_name": "Pulaski", "job_title": "Franchise Owner",
    },
    {
        "company_name": "Midstate Janitorial Supply",
        "company_website": "https://midstatejansupply.example",
        "city": "Harrisburg", "state": "Pennsylvania", "country": "United States",
        "industry": "Wholesale",
        "keywords": "janitorial supply, cleaning supplies, equipment sales, paper products",
        "company_description": "Distributor of cleaning chemicals, equipment and paper goods to cleaning contractors.",
        "company_size": 22, "first_name": "Ellen", "last_name": "Marsh", "job_title": "President",
    },
    {
        "company_name": "Crescent Pressure Washing",
        "company_website": "https://crescentpw.example",
        "city": "New Orleans", "state": "Louisiana", "country": "United States",
        "industry": "Facilities Services",
        "keywords": "pressure washing, soft wash, driveway cleaning, roof cleaning",
        "company_description": "Exterior pressure washing for homes and storefronts.",
        "company_size": 4, "first_name": "Marcus", "last_name": "Boudreaux", "job_title": "Owner",
    },
    {
        "company_name": "Bright Path Building Services",
        "company_website": "https://brightpathbuilding.example",
        "city": "Naperville", "state": "Illinois", "country": "United States",
        "industry": "Facilities Services",
        "keywords": "commercial cleaning, janitorial services, day porter, floor care",
        "company_description": "Nightly janitorial for medical office buildings and clinics across the western suburbs.",
        "company_size": 38, "first_name": "Renata", "last_name": "Kowalski", "job_title": "Owner",
    },
    {
        "company_name": "Harborline Facility Group",
        "company_website": "https://harborlinefacility.example",
        "city": "Bellevue", "state": "Washington", "country": "United States",
        "industry": "Facilities Services",
        "keywords": "facility services, warehouse cleaning, industrial cleaning, distribution centers",
        "company_description": "Industrial and warehouse cleaning crews for distribution and logistics sites.",
        "company_size": 55, "first_name": "Owen", "last_name": "Baptiste", "job_title": "Managing Partner",
    },
    {
        "company_name": "Vanta Clean Cooperative",
        "company_website": "",
        "city": "Tulsa", "state": "Oklahoma", "country": "United States",
        "industry": "Facilities Services",
        "keywords": "cleaning",
        "company_description": "",
        "company_size": 6, "first_name": "", "last_name": "", "job_title": "",
    },
]


def main():
    files = sorted(glob.glob(os.path.join(PROD, "cleaning__b*.json")))
    if not files:
        sys.exit("no recorded cleaning output at %s" % PROD)
    rows = []
    seen = set()
    for path in files:
        with open(path, "r", encoding="utf-8") as fh:
            for row in json.load(fh):
                domain = (row.get("company_domain") or "").lower()
                if not domain or domain in seen:
                    continue
                seen.add(domain)
                keep = dict((k, row.get(k)) for k in KEEP if row.get(k) not in (None, ""))
                # The address is what the pipeline has to earn. Drop it.
                keep.pop("email", None)
                rows.append(keep)
                if len(rows) >= 50:
                    break
        if len(rows) >= 50:
            break
    out = rows + NEGATIVES
    path = os.path.join(HERE, "source_cleaning_50.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print("wrote %s: %d real + %d handwritten = %d" % (path, len(rows), len(NEGATIVES), len(out)))


if __name__ == "__main__":
    main()
