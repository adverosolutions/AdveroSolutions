@direction LR
@spacing 60

(1 · Tracking Script: Page View Event) -> [2 · Filter Bots and ISPs]
[2 · Filter Bots and ISPs] -> [3 · IPinfo: Reverse IP to Company]
[3 · IPinfo: Reverse IP to Company] -> [4 · Behavioral Score · pages, time, pricing page]
[4 · Behavioral Score · pages, time, pricing page] -> {5 · Score Above Threshold?}
{5 · Score Above Threshold?} -> "true" -> [6 · Claude: Enrich and Summarize the Account]
{5 · Score Above Threshold?} -> "false" -> [5b · Below Threshold: Keep the Visit, No Alert]
[6 · Claude: Enrich and Summarize the Account] -> [7 · Upsert Account + Visit Activity]
[7 · Upsert Account + Visit Activity] -> [8 · Hot Visitor Alert to Sales]
(9 · Every Morning) -> [10 · Firecrawl: Crawl Watched Sources]
[10 · Firecrawl: Crawl Watched Sources] -> [11 · Claude: Extract Buying Signals]
[11 · Claude: Extract Buying Signals] -> {12 · Signal Found?}
{12 · Signal Found?} -> "true" -> [13 · Salesforce: Create Task on Account]
[13 · Salesforce: Create Task on Account] -> [14 · Buying Signal Digest to Sales]
(15 · Any Node Fails, Anywhere) -> [16 · Alert With a Link to the Failed Run]
[Claude] --> [6 · Claude: Enrich and Summarize the Account]
[MCP: Salesforce Account Lookup] --> [6 · Claude: Enrich and Summarize the Account]
[Account Summary, Fit Score, Suggested Next Step] --> [6 · Claude: Enrich and Summarize the Account]
[Claude 2] --> [11 · Claude: Extract Buying Signals]
