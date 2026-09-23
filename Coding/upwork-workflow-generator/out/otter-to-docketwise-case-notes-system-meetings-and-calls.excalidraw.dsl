@direction LR
@spacing 60

(1 - Otter AI: Meeting Transcript Ready) -> [2 - Microsoft 365: Find the Calendar Appointment for This Meeting]
[2 - Microsoft 365: Find the Calendar Appointment for This Meeting] -> [3 - Pull Client Name and Case Number From the Appointment]
[3 - Pull Client Name and Case Number From the Appointment] -> {4 - Case Identified From the Calendar?}
{4 - Case Identified From the Calendar?} -> "true" -> [9 - Docketwise: Search Matter by Client or Case Number]
{4 - Case Identified From the Calendar?} -> "false" -> [5 - Claude: Extract Client and Case References From the Transcript]
[5 - Claude: Extract Client and Case References From the Transcript] -> [9 - Docketwise: Search Matter by Client or Case Number]
(6 - RingCentral: Call Recording Available) -> [7 - RingCentral: Fetch the Recording and Caller ID]
[7 - RingCentral: Fetch the Recording and Caller ID] -> [8 - Docketwise: Match Contact by Phone Number]
[8 - Docketwise: Match Contact by Phone Number] -> {10 - Exactly One Matter Matched?}
[9 - Docketwise: Search Matter by Client or Case Number] -> {10 - Exactly One Matter Matched?}
{10 - Exactly One Matter Matched?} -> "true" -> [12 - Claude: Summarize Into a Case Note With Decisions, Deadlines and Follow Ups]
{10 - Exactly One Matter Matched?} -> "false" -> [11 - Email Staff to Confirm Which Matter This Belongs To]
[12 - Claude: Summarize Into a Case Note With Decisions, Deadlines and Follow Ups] -> [13 - Docketwise: Add the Note to the Matter]
[13 - Docketwise: Add the Note to the Matter] -> [[14 - Audit Log: Source, Matter and Link to the Note]]
(15 - Something Failed Anywhere in the Flow) -> [16 - Email the Office With the Transcript That Did Not File]
[Claude] --> [5 - Claude: Extract Client and Case References From the Transcript]
[Claude 2] --> [12 - Claude: Summarize Into a Case Note With Decisions, Deadlines and Follow Ups]
