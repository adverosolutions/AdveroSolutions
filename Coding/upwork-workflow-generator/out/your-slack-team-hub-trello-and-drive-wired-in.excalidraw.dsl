@direction LR
@spacing 60

(1 - Trello Card or Drive File Event Arrives) -> [2 - Private Channel Map]
[2 - Private Channel Map] -> [3 - Pick the Team Channel From the Map]
[3 - Pick the Team Channel From the Map] -> [4 - Build the Message]
[4 - Build the Message] -> {5 - Card Update or File Upload?}
{5 - Card Update or File Upload?} -> "true" -> [6 - Post the Card Update to the Team Channel]
{5 - Card Update or File Upload?} -> "false" -> [6b - Post the File Link and Who Uploaded It]
[6 - Post the Card Update to the Team Channel] -> {7 - Posted OK?}
[6b - Post the File Link and Who Uploaded It] -> {7 - Posted OK?}
{7 - Posted OK?} -> "true" -> [[9 - Log Every Notification]]
{7 - Posted OK?} -> "false" -> [8 - Alert Ops That the Post Failed]
[8 - Alert Ops That the Post Failed] -> [[9 - Log Every Notification]]
