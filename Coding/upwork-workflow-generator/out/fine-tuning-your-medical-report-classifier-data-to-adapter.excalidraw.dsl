@direction LR
@spacing 60

[1 - Clean the CSV: Dedupe, Normalize Formatting, Drop Unusable Rows] -> {2 - Any Labels Look Inconsistent or Mislabeled?}
{2 - Any Labels Look Inconsistent or Mislabeled?} -> "true" -> [2a - Return Suspect Rows to You to Confirm or Relabel]
[2a - Return Suspect Rows to You to Confirm or Relabel] -> [3 - Hold Out a Stratified Validation and Test Set]
{2 - Any Labels Look Inconsistent or Mislabeled?} -> "false" -> [3 - Hold Out a Stratified Validation and Test Set]
[3 - Hold Out a Stratified Validation and Test Set] -> [4 - Select a Lightweight Open Source Model for Your Categories]
[4 - Select a Lightweight Open Source Model for Your Categories] -> [5 - Convert Rows to the Model's Fine Tuning Format]
[5 - Convert Rows to the Model's Fine Tuning Format] -> [6 - Score the Base Model on the Test Set - Before Number]
[6 - Score the Base Model on the Test Set - Before Number] -> [7 - Train a LoRA Adapter, a Few Epochs, on Your Hardware or Cloud]
[7 - Train a LoRA Adapter, a Few Epochs, on Your Hardware or Cloud] -> [8 - Evaluate: Accuracy, per Category Precision and Recall, Confusion Matrix]
[8 - Evaluate: Accuracy, per Category Precision and Recall, Confusion Matrix] -> {9 - Beats Baseline, Including Recall on Urgent?}
{9 - Beats Baseline, Including Recall on Urgent?} -> "false" -> [9a - Iterate: Fix Labels, Reweight Classes, Adjust Epochs, Retrain]
[9a - Iterate: Fix Labels, Reweight Classes, Adjust Epochs, Retrain] --> [7 - Train a LoRA Adapter, a Few Epochs, on Your Hardware or Cloud]
{9 - Beats Baseline, Including Recall on Urgent?} -> "true" -> [10 - Save the Adapter Files and Inference Script]
[10 - Save the Adapter Files and Inference Script] -> [11 - Reproducible Code, Setup Instructions, Results Summary and Limitations]
