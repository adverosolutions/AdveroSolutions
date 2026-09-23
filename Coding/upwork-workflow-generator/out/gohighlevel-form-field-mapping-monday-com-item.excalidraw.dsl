@direction LR
@spacing 60

(GoHighLevel Form Submitted) -> [Map Form Fields to Monday.com Board Columns]
[Map Form Fields to Monday.com Board Columns] -> [Create New Item on the Monday.com Board]
[Create New Item on the Monday.com Board] -> {Item Created Successfully?}
{Item Created Successfully?} -> "true" -> [Return Success to GoHighLevel]
{Item Created Successfully?} -> "false" -> [Alert: Submission Did Not Sync to Monday.com]
