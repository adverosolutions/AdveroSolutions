@direction LR
@spacing 60

(1 · Every Weekday at 7am) -> [2 · Apollo: Pull Candidate Companies by Industry and Size]
[2 · Apollo: Pull Candidate Companies by Industry and Size] -> [3 · Work Through One Company at a Time]
[3 · Work Through One Company at a Time] -> "loop" -> [4 · Fit-Check Against Your Written Criteria]
[3 · Work Through One Company at a Time] -> "done" -> [14 · Slack: Daily Digest of Added, Rejected, and Reasons]
[4 · Fit-Check Against Your Written Criteria] -> {5 · Does It Fit, With High Confidence?}
{5 · Does It Fit, With High Confidence?} -> "true" -> [6 · Hunter: Find Decision-Maker by Domain and Title]
{5 · Does It Fit, With High Confidence?} -> "false" -> [[13 · Log the Decision: Added or Rejected, and Why]]
[6 · Hunter: Find Decision-Maker by Domain and Title] -> [7 · Hunter: Verify the Email Address]
[7 · Hunter: Verify the Email Address] -> {8 · Is the Email Deliverable?}
{8 · Is the Email Deliverable?} -> "true" -> [9 · Hunter: Check if Already in Any Campaign]
{8 · Is the Email Deliverable?} -> "false" -> [[13 · Log the Decision: Added or Rejected, and Why]]
[9 · Hunter: Check if Already in Any Campaign] -> {10 · Is This a Brand New Lead?}
{10 · Is This a Brand New Lead?} -> "true" -> {11 · Route by Segment}
{10 · Is This a Brand New Lead?} -> "false" -> [[13 · Log the Decision: Added or Rejected, and Why]]
{11 · Route by Segment} -> "Local Service" -> [12a · Hunter: Add to Local Service Campaign]
{11 · Route by Segment} -> "Medtech" -> [12b · Hunter: Add to Medtech Campaign]
{11 · Route by Segment} -> "B2B" -> [12c · Hunter: Add to B2B Campaign]
[12a · Hunter: Add to Local Service Campaign] -> [[13 · Log the Decision: Added or Rejected, and Why]]
[12b · Hunter: Add to Medtech Campaign] -> [[13 · Log the Decision: Added or Rejected, and Why]]
[12c · Hunter: Add to B2B Campaign] -> [[13 · Log the Decision: Added or Rejected, and Why]]
[[13 · Log the Decision: Added or Rejected, and Why]] --> [3 · Work Through One Company at a Time]
(15 · Any Node Fails, Anywhere) -> [16 · Slack: Alert With a Link to the Failed Run]
[Claude] --> [4 · Fit-Check Against Your Written Criteria]
[Read the Company Website and About Page] --> [4 · Fit-Check Against Your Written Criteria]
[Force: Fit Yes/No, Segment, Confidence, Reason] --> [4 · Fit-Check Against Your Written Criteria]
