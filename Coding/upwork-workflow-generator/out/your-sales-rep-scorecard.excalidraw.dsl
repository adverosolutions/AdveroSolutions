@direction LR
@spacing 60

(1 - GHL Event: New Lead, Appointment, Call, Contract, Payment) -> [2 - Normalize the Event: Type, Contact, Rep, Amount, Time]
[2 - Normalize the Event: Type, Contact, Rep, Amount, Time] -> {3 - Which Event?}
{3 - Which Event?} -> "New Lead" -> [4a - Credit the Contact Owner]
{3 - Which Event?} -> "Appointment" -> [4b - GHL: Read the Appointment's Assigned User From the Calendar]
{3 - Which Event?} -> "Contract Sent" -> [4c - Credit the Opportunity Owner]
{3 - Which Event?} -> "Payment" -> [4d - Credit the Opportunity Owner]
[4a - Credit the Contact Owner] -> {5 - Rep Resolved?}
[4b - GHL: Read the Appointment's Assigned User From the Calendar] -> {5 - Rep Resolved?}
[4c - Credit the Opportunity Owner] -> {5 - Rep Resolved?}
[4d - Credit the Opportunity Owner] -> {5 - Rep Resolved?}
{5 - Rep Resolved?} -> "false" -> [[5b - Unassigned Queue for a Human to Fix]]
{5 - Rep Resolved?} -> "true" -> [[6 - Append to the Events Tab]]
(7 - Every Night at 11pm) -> [[8 - Read Today's Events]]
[[8 - Read Today's Events]] -> [9 - Per Rep: Leads, Booked, Held, Contracts, Revenue]
[9 - Per Rep: Leads, Booked, Held, Contracts, Revenue] -> [10 - Ratios: Booked per Lead, Held per Booked, Cash per Lead]
[10 - Ratios: Booked per Lead, Held per Booked, Cash per Lead] -> [[11 - Update the Scorecard Tab, One Row per Rep per Day]]
[[11 - Update the Scorecard Tab, One Row per Rep per Day]] -> [12 - Post the Leaderboard]
(13 - Any Step Fails) -> [14 - Alert With the Failing Node]
