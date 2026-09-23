@direction LR
@spacing 60

(1 - New Lead From Your Website or Ad Form) -> [2 - Clean Up Name, Email, Phone and Source]
[2 - Clean Up Name, Email, Phone and Source] -> [3 - Drop Blank Submissions With No Email or Phone]
[3 - Drop Blank Submissions With No Email or Phone] -> [4 - OpenAI Scores the Lead Against Your Rules]
[4 - OpenAI Scores the Lead Against Your Rules] -> {5 - Qualified by Your Rules?}
{5 - Qualified by Your Rules?} -> "true" -> [6 - Match the Lead to the Right Team From Your Routing Table]
{5 - Qualified by Your Rules?} -> "false" -> [5b - Not Qualified: Keep the Score and Reason]
[6 - Match the Lead to the Right Team From Your Routing Table] -> [7 - Email the Team the Lead and Why It Qualified]
[6 - Match the Lead to the Right Team From Your Routing Table] -> [[8 - Add the Lead to Your Status Tracker]]
[5b - Not Qualified: Keep the Score and Reason] -> [[8 - Add the Lead to Your Status Tracker]]
(9 - Every Morning: Start the Lead Report) -> [[10 - Read Every Lead in the Tracker]]
[[10 - Read Every Lead in the Tracker]] -> [11 - Count Leads by Source, Team and Status]
[11 - Count Leads by Source, Team and Status] -> [[12 - Refresh Your Dashboard Tab]]
[[12 - Refresh Your Dashboard Tab]] -> [13 - Email You the Morning Lead Numbers]
(14 - If Any Step Fails) -> [15 - Email You the Failed Step and a Link to the Run]
[OpenAI - Scores and Qualifies the Lead] --> [4 - OpenAI Scores the Lead Against Your Rules]
[Parser - Score, Team and Reason] --> [4 - OpenAI Scores the Lead Against Your Rules]
