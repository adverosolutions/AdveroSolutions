@direction LR
@spacing 60

(1 - Lead Capture Form Submitted) -> [2 - Tag the Contact lead-form]
[2 - Tag the Contact lead-form] -> [3 - Save the Lead Source on the Contact]
[3 - Save the Lead Source on the Contact] -> [4 - Tell the Team a New Lead Came In]
[4 - Tell the Team a New Lead Came In] -> [5 - Open the Opportunity at the New Lead Stage]
[5 - Open the Opportunity at the New Lead Stage] -> [6 - Text Them Right Away]
[6 - Text Them Right Away] -> [7 - Email Them the Booking Link]
[7 - Email Them the Booking Link] -> [8 - Wait 1 Day]
[8 - Wait 1 Day] -> [9 - Text: Still Want to Chat]
[9 - Text: Still Want to Chat] -> [10 - Wait 2 Days]
[10 - Wait 2 Days] -> [11 - Email: Two Quick Questions Before the Call]
[11 - Email: Two Quick Questions Before the Call] -> [12 - Wait 3 Days]
[12 - Wait 3 Days] -> [13 - Text: Last Check In]
[13 - Text: Last Check In] -> [14 - Wait 2 Days for a Reply to the Last Text]
[14 - Wait 2 Days for a Reply to the Last Text] -> [15 - Move the Opportunity to No Response]
[15 - Move the Opportunity to No Response] -> [16 - Give the Team a Task to Call Them Once]
[16 - Give the Team a Task to Call Them Once] -> [17 - Goal: They Replied or Booked]
(1 - Lead Replied on Any Channel) -> {2 - Is This a Lead in the Follow-Up?}
{2 - Is This a Lead in the Follow-Up?} -> "true" -> [3 - Tag the Contact lead-engaged]
[3 - Tag the Contact lead-engaged] -> [4 - Move the Opportunity to Replied]
[4 - Move the Opportunity to Replied] -> [5 - Text the Owner to Answer Now]
(1 - Appointment Booked on the Calendar) -> {2 - Is This a Lead in the Follow-Up? 2}
{2 - Is This a Lead in the Follow-Up? 2} -> "true" -> [3 - Tag the Contact lead-engaged 2]
[3 - Tag the Contact lead-engaged 2] -> [4 - Move the Opportunity to Call Booked]
[4 - Move the Opportunity to Call Booked] -> [5 - Email the Owner the Booking]
