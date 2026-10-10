---
name: overture-places-free-source
description: Overture Maps Places = free, open (Meta+Microsoft) US business dataset with websites/emails/phones by category; queried with DuckDB in ~3 min (2026-10-08); best free local-business source
metadata:
  type: reference
---

Overture Maps Foundation "places" theme is a free public dataset (open license, monthly releases). The release 2026-09-23.1 is 16 parquet files, 11 GB, at `s3://overturemaps-us-west-2/release/<release>/theme=places/type=place/*.parquet`. It is anonymous S3, so no key is needed. List releases with `https://overturemaps-us-west-2.s3.amazonaws.com/?list-type=2&prefix=release/&delimiter=/`.

**How to query:** use DuckDB with `httpfs` and `s3_region='us-west-2'`. Filter by bbox plus `addresses[1].country='US'` and on `taxonomy."primary"` / `basic_category` / `taxonomy.alternates`. Useful columns are websites[], emails[], phones[], addresses[], operating_status and confidence. A full US niche extract took 194 s on 2026-10-08. Use plain-SQL domain parsing: Python UDFs need numpy, which is not installed in the scratch venv.

**US counts (2026-09-23.1, primary category):** insurance_agency 229k, accountant 91k, hvac_service 60k, roofing 56k, landscaping 49k, employment_agency 49k, it_service_and_computer_repair 48k, plumbing 47k, electrician 42k, marketing_agency 39k, advertising_agency 31k, home_cleaning 34k, tax_service 35k, pest_control_service 24k, janitorial_service 9k, office_cleaning 4.6k.

**Electrician detail:**
- 34.8k have a website (27.4k distinct domains), 11.3k list an email (2.4k generic, 5.2k gmail/yahoo-type), 41k have a phone, 32.5k are status open.
- Only 12.8k domains overlap the repo's 12M Maps file, so the union is 42.3k electrician domains.

**How to apply:** For local trades, union Overture with the Maps file (and live RapidAPI zip sweeps for freshness), then find owner emails. State licence boards are another free owner-name source: TX TDLR posts daily CSVs, FL DBPR has an electrical licensee file. Lorenzo floated rotating fresh free accounts on paid tools (PhantomBuster-style); Claude does not build around that. See [[list-builder-maps-quickenrich]].
