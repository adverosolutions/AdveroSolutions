@direction LR
@spacing 60

[1 - Clean the 800 Reports, Send Suspect Labels Back to You] -> [2 - Set Aside a Test Set Before Anything Trains]
[2 - Set Aside a Test Set Before Anything Trains] -> [3 - Pick a Small Open Source Model That Fits Your Categories]
[3 - Pick a Small Open Source Model That Fits Your Categories] -> [4 - Score the Untouched Model First]
[4 - Score the Untouched Model First] -> [5 - Train a Small Adapter on Your Examples]
[5 - Train a Small Adapter on Your Examples] -> {6 - Does It Beat the Baseline, Especially on Urgent?}
{6 - Does It Beat the Baseline, Especially on Urgent?} -> "false" -> [6a - Fix Labels, Rebalance, Train Again]
[6a - Fix Labels, Rebalance, Train Again] --> [5 - Train a Small Adapter on Your Examples]
{6 - Does It Beat the Baseline, Especially on Urgent?} -> "true" -> [7 - Adapter Files, One Command Script, Short Write Up]
