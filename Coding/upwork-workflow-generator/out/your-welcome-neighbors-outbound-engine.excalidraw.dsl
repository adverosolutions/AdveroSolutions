@direction LR
@spacing 60

(1 - Every Weekday at 6am, Next Target Metro) -> [2 - Google Maps: Pull HVAC, Dental, Roofing and Plumbing Businesses in the Zip Codes]
[2 - Google Maps: Pull HVAC, Dental, Roofing and Plumbing Businesses in the Zip Codes] -> [3 - Clay: Enrich the Business, Website, Phone, Size and Reviews]
[3 - Clay: Enrich the Business, Website, Phone, Size and Reviews] -> [4 - Clay: Find the Owner or Decision Maker]
[4 - Clay: Find the Owner or Decision Maker] -> [5 - Clay Waterfall: Email From 3 Providers, Then Verify It Is Deliverable]
[5 - Clay Waterfall: Email From 3 Providers, Then Verify It Is Deliverable] -> {6 - Deliverable and Owner Found?}
{6 - Deliverable and Owner Found?} -> "true" -> [7 - Claude Scores Fit: Serves New Movers, Size, Reviews, Ads Running]
{6 - Deliverable and Owner Found?} -> "false" -> [[9 - Park It: Log the Reason, Retry Next Cycle]]
[7 - Claude Scores Fit: Serves New Movers, Size, Reviews, Ads Running] -> {8 - Score 7 or Higher?}
{8 - Score 7 or Higher?} -> "true" -> [10 - Instantly: Add Lead to the Segment Campaign With the First Line and Follow-Ups]
{8 - Score 7 or Higher?} -> "false" -> [[9 - Park It: Log the Reason, Retry Next Cycle]]
(11 - Instantly: Reply Comes In) -> [12 - Claude Sorts the Reply: Interested, Question, Not Now, Unsubscribe]
[12 - Claude Sorts the Reply: Interested, Question, Not Now, Unsubscribe] -> {13 - Route the Reply}
{13 - Route the Reply} -> "Interested" -> [14 - GoHighLevel: Create the Lead and Notify Sales]
{13 - Route the Reply} -> "Question" -> [14b - Hand to a Human]
{13 - Route the Reply} -> "Not Now" -> [[14c - Nurture List, Retry in 90 Days]]
{13 - Route the Reply} -> "Unsubscribe" -> [14d - Instantly: Unsubscribe Everywhere]
[14 - GoHighLevel: Create the Lead and Notify Sales] -> [[15 - Daily Scorecard: Sent, Delivered, Replies, Positive, Booked]]
(16 - Any Step Fails) -> [17 - Alert With the Failing Node]
[10 - Instantly: Add Lead to the Segment Campaign With the First Line and Follow-Ups] -> [[15 - Daily Scorecard: Sent, Delivered, Replies, Positive, Booked]]
[Claude] --> [7 - Claude Scores Fit: Serves New Movers, Size, Reviews, Ads Running]
[Read Their Website and Google Profile] --> [7 - Claude Scores Fit: Serves New Movers, Size, Reviews, Ads Running]
[Score 1 to 10, Segment, First Line] --> [7 - Claude Scores Fit: Serves New Movers, Size, Reviews, Ads Running]
[Claude 2] --> [12 - Claude Sorts the Reply: Interested, Question, Not Now, Unsubscribe]
