@direction LR
@spacing 60

(1 - Daily Prospect Run) -> [2 - Apify: Scrape Target Companies From Google Maps and LinkedIn]
[2 - Apify: Scrape Target Companies From Google Maps and LinkedIn] -> [3 - Take One Company at a Time]
[3 - Take One Company at a Time] -> "loop" -> [4 - Snov.io: Find the Decision Maker's Email]
[3 - Take One Company at a Time] -> "done" -> [[11 - Log Every Company Added and Rejected, With the Reason]]
[4 - Snov.io: Find the Decision Maker's Email] -> [5 - Snov.io: Verify That Email Is Deliverable]
[5 - Snov.io: Verify That Email Is Deliverable] -> {6 - Did the Address Come Back Deliverable?}
{6 - Did the Address Come Back Deliverable?} -> "true" -> [8 - Research the Company and Write a Personalized First Line]
{6 - Did the Address Come Back Deliverable?} -> "false" -> [7 - Record Why This Company Was Skipped]
[8 - Research the Company and Write a Personalized First Line] -> {9 - Is the Fit Score Above Your Threshold?}
{9 - Is the Fit Score Above Your Threshold?} -> "true" -> [10 - Snov.io: Add the Prospect to the Campaign With Custom Fields]
{9 - Is the Fit Score Above Your Threshold?} -> "false" -> [7 - Record Why This Company Was Skipped]
[10 - Snov.io: Add the Prospect to the Campaign With Custom Fields] --> [3 - Take One Company at a Time]
[7 - Record Why This Company Was Skipped] --> [3 - Take One Company at a Time]
(12 - A Reply Comes Back From Snov.io) -> [13 - OpenAI: Read the Reply and Label It Interested, Not Now, or Unsubscribe]
[13 - OpenAI: Read the Reply and Label It Interested, Not Now, or Unsubscribe] -> {14 - Route on What They Actually Said}
{14 - Route on What They Actually Said} -> "Interested" -> [14a - Send Interested Leads Straight to You]
{14 - Route on What They Actually Said} -> "Not Now" -> [14b - Snov.io: Pause the Sequence and Try Again Later]
{14 - Route on What They Actually Said} -> "Unsubscribe" -> [14c - Snov.io: Unsubscribe Them and Stop All Email]
(15 - Any Step Fails, Anywhere) -> [16 - Alert You With a Link to the Failed Run]
[OpenAI] --> [8 - Research the Company and Write a Personalized First Line]
[Read the Company Website] --> [8 - Research the Company and Write a Personalized First Line]
[Force Back a First Line, an Angle, and a Fit Score] --> [8 - Research the Company and Write a Personalized First Line]
