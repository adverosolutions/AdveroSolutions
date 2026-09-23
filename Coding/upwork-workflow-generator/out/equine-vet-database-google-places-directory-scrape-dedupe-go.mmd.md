# Equine Vet Database — Google Places + Directory Scrape → Dedupe → Google Sheets

```mermaid
flowchart LR
    subgraph sec_places["1 · SOURCE: GOOGLE PLACES"]
        direction TB
        trig(["Weekly Automated Refresh"])
        next_country["Split Country List Into One Batch at a Time"]
        places_query["Query Google Places API for Equine Vets in This Country"]
        parse_places["Parse Results Into Name, Address, Phone, Website"]
        more_countries{"More Countries Left to Query?"}
    end
    subgraph sec_directory["2 · SOURCE: DIRECTORY SCRAPE"]
        direction TB
        next_directory["Split Directory URL List Into One Batch at a Time"]
        fetch_html["Fetch the Directory Page HTML"]
        parse_html["Parse HTML and Extract Name, Clinic, Email, Phone"]
        normalize_dir["Normalize Directory Fields to Match the Places Schema"]
        more_directories{"More Directory Pages Left to Parse?"}
    end
    subgraph sec_merge["3 · DEDUPE & MERGE"]
        direction TB
        merge_sources["Merge Google Places and Directory Records"]
        dedupe["Deduplicate by Name, Country, and Matching Phone or Website"]
    end
    subgraph sec_output["4 · WRITE TO SHEETS"]
        direction TB
        write_sheets[("Write Clean Records to Google Sheets<br/><i>googleSheets</i>")]
        log_summary["Log Run Summary: New, Updated, Duplicates Skipped"]
    end
    trig --> next_country
    trig --> next_directory
    next_country --> places_query
    places_query --> parse_places
    parse_places --> more_countries
    more_countries -.->|true| next_country
    more_countries -->|false| merge_sources
    next_directory --> fetch_html
    fetch_html --> parse_html
    parse_html --> normalize_dir
    normalize_dir --> more_directories
    more_directories -.->|true| next_directory
    more_directories -->|false| merge_sources
    merge_sources --> dedupe
    dedupe --> write_sheets
    write_sheets --> log_summary
    style sec_places fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_directory fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_merge fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_output fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 · SOURCE: GOOGLE PLACES** — Loops through the country list and queries the official Places API for equine vets in each one.
- **2 · SOURCE: DIRECTORY SCRAPE** — Loops through the directory URLs, fetches the HTML, and parses contact data in code, the BeautifulSoup-equivalent step run inside the workflow.
- **3 · DEDUPE & MERGE** — Both sources land in one merge, then get deduplicated by name, country, and matching phone or website.
- **4 · WRITE TO SHEETS** — Clean records write straight to Google Sheets, with a run summary logged for visibility.
