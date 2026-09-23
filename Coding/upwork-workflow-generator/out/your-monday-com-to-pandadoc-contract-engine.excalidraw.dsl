@direction LR
@spacing 60

(1 - Monday.com Item Moved to Ready for Contract) -> [2 - Monday.com: Fetch the Item and Column Values]
[2 - Monday.com: Fetch the Item and Column Values] -> [3 - Monday.com: Download the Contract PDF]
[3 - Monday.com: Download the Contract PDF] -> [4 - Extract Text From PDF]
[4 - Extract Text From PDF] -> {5 - Text Found in the PDF?}
{5 - Text Found in the PDF?} -> "true" -> [6 - Extract Contract Fields to JSON Schema]
{5 - Text Found in the PDF?} -> "false" -> [5b - OCR the Scanned Pages Instead]
[5b - OCR the Scanned Pages Instead] -> [6 - Extract Contract Fields to JSON Schema]
[6 - Extract Contract Fields to JSON Schema] -> {7 - Required Fields Present and Amounts Parse?}
{7 - Required Fields Present and Amounts Parse?} -> "true" -> [8 - PandaDoc: Create Document From Template]
{7 - Required Fields Present and Amounts Parse?} -> "false" -> [7b - Hold the Item and Ask a Human to Confirm]
[8 - PandaDoc: Create Document From Template] -> [9 - Wait 20 Seconds for the Draft to Build]
[9 - Wait 20 Seconds for the Draft to Build] -> {10 - Is the Document in Draft Status Yet?}
{10 - Is the Document in Draft Status Yet?} -> "true" -> [11 - PandaDoc: Send For Signature]
{10 - Is the Document in Draft Status Yet?} --> [9 - Wait 20 Seconds for the Draft to Build]
[11 - PandaDoc: Send For Signature] -> [12 - Monday.com: Write Back the Link and Status]
(13 - Any Step Fails, Anywhere in the Run) -> [14 - Alert the Team With the Failed Run Link]
[14 - Alert the Team With the Failed Run Link] -> [15 - Monday.com: Flag the Item as Contract Failed]
[GPT-4o] --> [6 - Extract Contract Fields to JSON Schema]
[Schema: Party, Address, Value, Term, Start Date] --> [6 - Extract Contract Fields to JSON Schema]
