@direction LR
@spacing 60

(1 - Workiz: Job Assigned to Me) -> [2 - Pull Customer, Job Type, Address, Time Window]
[2 - Pull Customer, Job Type, Address, Time Window] -> [3 - OpenAI: Write the Personalized First SMS From Your Template]
[3 - OpenAI: Write the Personalized First SMS From Your Template] -> [4 - Quo / OpenPhone: Send SMS From Your Existing Number]
[4 - Quo / OpenPhone: Send SMS From Your Existing Number] -> [[5 - Log Job + Message Sent]]
(6 - Quo / OpenPhone: Customer Replied) -> [7 - OpenAI: Understand the Reply and Pick a Pre-Approved Template]
[7 - OpenAI: Understand the Reply and Pick a Pre-Approved Template] -> [8 - Suggest Reply to Rep: Approve or Edit]
(9 - Rep Approved or Edited) -> [10 - Quo / OpenPhone: Send the Approved Reply]
[10 - Quo / OpenPhone: Send the Approved Reply] -> [[11 - Log Reply + Approval]]
(12 - Any Step in the Scenario Fails) -> [13 - Alert Me With the Job and What Broke]
[OpenAI] --> [3 - OpenAI: Write the Personalized First SMS From Your Template]
[OpenAI 2] --> [7 - OpenAI: Understand the Reply and Pick a Pre-Approved Template]
[Approved Template Library] --> [7 - OpenAI: Understand the Reply and Pick a Pre-Approved Template]
[Intent + Suggested Reply + Confidence] --> [7 - OpenAI: Understand the Reply and Pick a Pre-Approved Template]
