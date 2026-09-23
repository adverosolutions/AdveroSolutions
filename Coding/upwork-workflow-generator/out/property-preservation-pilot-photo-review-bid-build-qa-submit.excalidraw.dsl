@direction LR
@spacing 60

(1 · New Work Order From PPW · API, Export, or RPA Feed) -> [2 · PPW: Pull Work Order Notes and Photos]
[2 · PPW: Pull Work Order Notes and Photos] -> [3 · One Photo at a Time]
[3 · One Photo at a Time] -> "loop" -> [4 · Claude Vision: Describe Condition and Check Scope vs Instructions]
[4 · Claude Vision: Describe Condition and Check Scope vs Instructions] --> [3 · One Photo at a Time]
[3 · One Photo at a Time] -> "done" -> [5 · Combine Photo Findings]
[5 · Combine Photo Findings] -> {6 · Photos Complete and In Scope?}
{6 · Photos Complete and In Scope?} -> "false" -> [6a · Flag: Missing or Off-Scope Photos, Request Re-Upload]
{6 · Photos Complete and In Scope?} -> "true" -> [7 · Pricing DB: Historical Bids by Geography and Work Order Type]
[7 · Pricing DB: Historical Bids by Geography and Work Order Type] -> [8 · Claude: Build Bid Sheet Line Items]
[8 · Claude: Build Bid Sheet Line Items] -> [9 · QA Pass: Flag Underpriced, Overpriced, Incomplete]
[9 · QA Pass: Flag Underpriced, Overpriced, Incomplete] -> {10 · QA Clean?}
{10 · QA Clean?} -> "false" -> [10a · Bid Needs Human Review, With the Reasons Attached]
{10 · QA Clean?} -> "true" -> [11 · Human Approval: One-Tap Submit]
[11 · Human Approval: One-Tap Submit] -> [12 · PPW: Submit Bid]
[12 · PPW: Submit Bid] -> [[13 · Log the Bid, the Pricing Basis, and the QA Result]]
(14 · Any Step Fails, Anywhere) -> [15 · Alert Ops With the Work Order Number and a Link to the Run]
[Claude] --> [4 · Claude Vision: Describe Condition and Check Scope vs Instructions]
[Claude 2] --> [8 · Claude: Build Bid Sheet Line Items]
[Historical Pricing Lookup] --> [8 · Claude: Build Bid Sheet Line Items]
[Client Pricing Rules] --> [8 · Claude: Build Bid Sheet Line Items]
[Force Line Items, Quantities, Unit Prices, and Margin] --> [8 · Claude: Build Bid Sheet Line Items]
[Claude 3] --> [9 · QA Pass: Flag Underpriced, Overpriced, Incomplete]
