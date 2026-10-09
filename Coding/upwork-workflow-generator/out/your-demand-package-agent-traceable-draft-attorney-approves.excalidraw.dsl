@direction LR
@spacing 60

(1 - Case Marked Ready for Demand in Your Case System) -> [2 - Google Drive: Pull Every Record and Bill, Page by Page]
[2 - Google Drive: Pull Every Record and Bill, Page by Page] -> [3 - Claude Extracts Every Visit, Charge and Its Source Page]
[3 - Claude Extracts Every Visit, Charge and Its Source Page] -> [4 - Total Medical Expenses by Provider, Flag Gaps and Missing Records]
[4 - Total Medical Expenses by Provider, Flag Gaps and Missing Records] -> [5 - Claude Drafts the Demand Letter From Extracted Facts Only]
[5 - Claude Drafts the Demand Letter From Extracted Facts Only] -> [6 - Google Docs: Save the Draft With the Exhibit Index]
[6 - Google Docs: Save the Draft With the Exhibit Index] -> [7 - Gmail: Attorney Approves or Sends Edits Back]
[7 - Gmail: Attorney Approves or Sends Edits Back] -> {8 - Approved by the Attorney?}
{8 - Approved by the Attorney?} -> "true" -> [9 - Export the Demand Package as Word and PDF]
{8 - Approved by the Attorney?} --> [5 - Claude Drafts the Demand Letter From Extracted Facts Only]
(10 - Any Step Fails) -> [11 - Gmail: Alert the Case Manager, No Medical Details]
[Claude - Reads the Records and Bills] --> [3 - Claude Extracts Every Visit, Charge and Its Source Page]
[Extraction Result: Each Fact With Its File and Page] --> [3 - Claude Extracts Every Visit, Charge and Its Source Page]
[Claude - Writes the Demand Draft] --> [5 - Claude Drafts the Demand Letter From Extracted Facts Only]
