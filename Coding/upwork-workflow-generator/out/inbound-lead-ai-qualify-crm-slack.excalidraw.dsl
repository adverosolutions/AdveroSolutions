@direction LR
@spacing 60

(New Lead Submitted) -> [Normalize Lead Fields]
[Normalize Lead Fields] -> [Enrich Company Domain]
[Enrich Company Domain] -> [Score Lead vs ICP]
[Score Lead vs ICP] -> {Score ≥ 70?}
{Score ≥ 70?} -> "true" -> [Upsert CRM Contact]
{Score ≥ 70?} -> "false" -> [[Add to Nurture List]]
[Upsert CRM Contact] -> [Alert #sales]
[Alert #sales] -> [Confirm to Visitor]
[GPT-4.1] --> [Score Lead vs ICP]
[Structured Score Output] --> [Score Lead vs ICP]
