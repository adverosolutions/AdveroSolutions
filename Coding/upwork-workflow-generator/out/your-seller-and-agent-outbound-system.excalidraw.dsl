@direction LR
@spacing 60

(1 - Every Weekday at 6am) -> [2 - Pull Fresh Distressed-Owner Records: Probate, Tax Lien, Pre-Foreclosure]
(1 - Every Weekday at 6am) -> [2b - Pull Agents With Aged or Off-Market Listings]
[2 - Pull Fresh Distressed-Owner Records: Probate, Tax Lien, Pre-Foreclosure] -> [3 - One Queue, Tagged Seller or Agent]
[2b - Pull Agents With Aged or Off-Market Listings] -> [3 - One Queue, Tagged Seller or Agent]
[3 - One Queue, Tagged Seller or Agent] -> [4 - Verify Every Email]
[4 - Verify Every Email] -> {5 - Deliverable?}
{5 - Deliverable?} -> "true" -> [[6 - Already Contacted or Opted Out?]]
{5 - Deliverable?} -> "false" -> [[5b - Suppressed: Bounces and Catch-Alls]]
[[6 - Already Contacted or Opted Out?]] -> {7 - New Contact?}
{7 - New Contact?} -> "true" -> [8 - Claude Writes the Plain-Text First Line and Picks the Angle]
{7 - New Contact?} -> "false" -> [[5b - Suppressed: Bounces and Catch-Alls]]
[8 - Claude Writes the Plain-Text First Line and Picks the Angle] -> {9 - Seller or Agent?}
{9 - Seller or Agent?} -> "Seller" -> [10a - Instantly: Add to the Seller Sequence]
{9 - Seller or Agent?} -> "Agent" -> [10b - Instantly: Add to the Agent Sequence]
(11 - Instantly: Reply Comes In) -> [12 - Sort the Reply: Interested, Question, Not Now, Remove]
[12 - Sort the Reply: Interested, Question, Not Now, Remove] -> {13 - Route}
{13 - Route} -> "Interested" -> [14 - CRM: Create the Lead and Alert Acquisitions]
{13 - Route} -> "Question" -> [14b - Hand to a Human]
{13 - Route} -> "Not Now" -> [[14c - Nurture, Retry in 90 Days]]
{13 - Route} -> "Remove" -> [14d - Instantly: Unsubscribe and Suppress]
[10a - Instantly: Add to the Seller Sequence] -> [[15 - Daily Scorecard: Sent, Bounce, Reply, Positive, Appointments]]
[10b - Instantly: Add to the Agent Sequence] -> [[15 - Daily Scorecard: Sent, Bounce, Reply, Positive, Appointments]]
[14 - CRM: Create the Lead and Alert Acquisitions] -> [[15 - Daily Scorecard: Sent, Bounce, Reply, Positive, Appointments]]
(16 - Any Step Fails) -> [17 - Alert With the Failing Node]
[Claude] --> [8 - Claude Writes the Plain-Text First Line and Picks the Angle]
[Read the Property Record or Listing] --> [8 - Claude Writes the Plain-Text First Line and Picks the Angle]
[First Line, Angle, Campaign] --> [8 - Claude Writes the Plain-Text First Line and Picks the Angle]
[Claude 2] --> [12 - Sort the Reply: Interested, Question, Not Now, Remove]
