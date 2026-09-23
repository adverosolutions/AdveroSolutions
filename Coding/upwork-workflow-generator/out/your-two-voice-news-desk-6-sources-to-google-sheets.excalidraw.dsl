@direction LR
@spacing 60

(1 - Every Morning at 6am) -> [2 - Load the 6 Source Feeds]
[2 - Load the 6 Source Feeds] -> [3 - Fetch the RSS Feed]
[3 - Fetch the RSS Feed] -> {4 - Feed Reachable?}
{4 - Feed Reachable?} -> "true" -> [6 - Split Into One Story per Item]
{4 - Feed Reachable?} -> "false" -> [[5 - Log the Dead Source]]
[6 - Split Into One Story per Item] -> [7 - Keep Only Topic Relevant Stories]
[7 - Keep Only Topic Relevant Stories] -> [[8 - Look Up What We Already Published]]
[[8 - Look Up What We Already Published]] -> {9 - New Story?}
{9 - New Story?} -> "true" -> [10 - Rewrite in Style A, Newsroom]
{9 - New Story?} --> [6 - Split Into One Story per Item]
[10 - Rewrite in Style A, Newsroom] -> [11 - Rewrite in Style B, Editorial Column]
[11 - Rewrite in Style B, Editorial Column] -> [[12 - Write Both Versions to the Review Sheet]]
[[12 - Write Both Versions to the Review Sheet]] -> [[13 - Load the 20 Topic Prompts]]
[[13 - Load the 20 Topic Prompts]] -> [14 - Write the Topic Article]
[14 - Write the Topic Article] -> [[15 - Add the Originals to the Same Sheet]]
(16 - Any Node Fails, Anywhere) -> [17 - Alert: Pipeline Failed]
[GPT-4o] --> [10 - Rewrite in Style A, Newsroom]
[GPT-4o 2] --> [11 - Rewrite in Style B, Editorial Column]
[GPT-4o 3] --> [14 - Write the Topic Article]
