@direction LR
@spacing 60

[1 - Read the CSV and Drop Exact Duplicate Reports] -> [2 - Catch Near Duplicates and Normalize the Formatting]
[2 - Catch Near Duplicates and Normalize the Formatting] -> {3 - Do Any Rows Look Mislabeled?}
{3 - Do Any Rows Look Mislabeled?} -> "true" -> [3a - Send Those Rows Back for You to Confirm]
{3 - Do Any Rows Look Mislabeled?} -> "false" -> [4 - Hold Out a Balanced Test Set Before Anything Trains]
[3a - Send Those Rows Back for You to Confirm] -> [4 - Hold Out a Balanced Test Set Before Anything Trains]
[4 - Hold Out a Balanced Test Set Before Anything Trains] -> [5 - Choose a Small Classifier or a Small Instruct Model]
[5 - Choose a Small Classifier or a Small Instruct Model] -> [6 - Decide If Each Answer Needs a Written Reason]
[6 - Decide If Each Answer Needs a Written Reason] -> [7 - Convert Every Row Into the Training Format]
[7 - Convert Every Row Into the Training Format] -> [8 - Score the Untouched Model on the Held Out Set]
[8 - Score the Untouched Model on the Held Out Set] -> [9 - Write Down the Baseline Accuracy per Category]
[9 - Write Down the Baseline Accuracy per Category] -> [10 - Train a LoRA Adapter for a Few Short Epochs]
[10 - Train a LoRA Adapter for a Few Short Epochs] -> [11 - Score the Tuned Model on the Same Test Set]
[11 - Score the Tuned Model on the Same Test Set] -> [12 - Build the Confusion Matrix and per Class Recall]
[12 - Build the Confusion Matrix and per Class Recall] -> {13 - Does It Beat the Baseline on Urgent Recall?}
{13 - Does It Beat the Baseline on Urgent Recall?} -> "false" -> [13a - Fix Labels, Weight Urgent Higher, Train Again]
[13a - Fix Labels, Weight Urgent Higher, Train Again] --> [10 - Train a LoRA Adapter for a Few Short Epochs]
{13 - Does It Beat the Baseline on Urgent Recall?} -> "true" -> [14 - Save the Adapter Files and the Training Code]
[14 - Save the Adapter Files and the Training Code] -> [15 - One Command Script to Classify a New Report]
[15 - One Command Script to Classify a New Report] -> [16 - Write Up Data, Model, Results, Limits and Cost]
