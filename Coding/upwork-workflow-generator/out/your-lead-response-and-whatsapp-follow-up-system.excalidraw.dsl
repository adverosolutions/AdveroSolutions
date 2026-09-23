@direction LR
@spacing 60

(1 - New Lead Writes In From Web Form, IG or FB DM) -> [2 - Normalize the Lead]
[2 - Normalize the Lead] -> [[3 - Save the Lead in Supabase]]
[[3 - Save the Lead in Supabase]] -> [4 - Instant Alert to the Team]
[4 - Instant Alert to the Team] -> [5 - WhatsApp via Twilio: Instant Reply With Booking Link]
[5 - WhatsApp via Twilio: Instant Reply With Booking Link] -> [6 - Wait 1 Day]
[6 - Wait 1 Day] -> {7 - Booked or Replied?}
{7 - Booked or Replied?} -> "true" -> [8 - WhatsApp: Confirm the Appointment]
[8 - WhatsApp: Confirm the Appointment] -> [9 - Put It on the Calendar]
{7 - Booked or Replied?} -> "false" -> [8b - WhatsApp: Gentle Follow-Up]
[8b - WhatsApp: Gentle Follow-Up] -> [9b - Wait 2 Days]
[9b - Wait 2 Days] --> {7 - Booked or Replied?}
(1b - WhatsApp Reply Comes In From Twilio) -> [10 - Classify the Reply]
[10 - Classify the Reply] -> {11 - Route: Book, Question, Stop}
{11 - Route: Book, Question, Stop} -> "Book" -> [12 - Book the Appointment on the Calendar]
{11 - Route: Book, Question, Stop} -> "Question" -> [13 - Hand to a Human]
{11 - Route: Book, Question, Stop} -> "Stop" -> [[14 - Mark Opted Out]]
(15 - Any Step Fails, Anywhere) -> [16 - Alert: Flow Failed]
[GPT-4o] --> [10 - Classify the Reply]
