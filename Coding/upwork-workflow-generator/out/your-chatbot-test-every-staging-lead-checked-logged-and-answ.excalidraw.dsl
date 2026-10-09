@direction LR
@spacing 60

(1 - Chatbot Snippet on Staging Posts the Lead Here) -> [2 - Check Name, Email, Phone and Message Arrived]
[2 - Check Name, Email, Phone and Message Arrived] -> [[3 - Log Every Capture to the Test Sheet]]
[[3 - Log Every Capture to the Test Sheet]] -> {4 - All Four Fields There and Valid?}
{4 - All Four Fields There and Valid?} -> "true" -> [5 - Tell the Chatbot: Lead Received]
{4 - All Four Fields There and Valid?} -> "false" -> [5b - Flag the Missing Field to Your Test Inbox]
[5b - Flag the Missing Field to Your Test Inbox] -> [5c - Tell the Chatbot Which Field Was Missing]
[5 - Tell the Chatbot: Lead Received] -> [6 - Next Phase: HubSpot Creates the Contact From the Chat]
[6 - Next Phase: HubSpot Creates the Contact From the Chat] -> [7 - Google Calendar: Book the Call Time They Asked For]
(8 - Any Step Fails) -> [9 - Email You the Failed Step and a Link to the Run]
