@direction LR
@spacing 60

(1 - Sales Request Form Submitted) -> [2 - Tag the Contact sales-request]
[2 - Tag the Contact sales-request] -> [3 - Open the Request in the Sales Pipeline]
[3 - Open the Request in the Sales Pipeline] -> [4 - Call You, Whisper the Details, Then Connect]
[4 - Call You, Whisper the Details, Then Connect] -> {5 - Did the Call Connect}
{5 - Did the Call Connect} -> "true" -> [6 - Move the Request to Spoke With]
{5 - Did the Call Connect} -> "false" -> [7 - Text: Sorry I Missed You]
[7 - Text: Sorry I Missed You] -> [8 - Wait 1 Day]
[8 - Wait 1 Day] -> [9 - Email: Getting You on the Schedule]
[9 - Email: Getting You on the Schedule] -> [10 - Wait 2 Days]
[10 - Wait 2 Days] -> [11 - Manual Call Task for You]
[11 - Manual Call Task for You] -> [12 - Wait 3 Days]
[12 - Wait 3 Days] -> [13 - Text: Still Want This on the Calendar]
[13 - Text: Still Want This on the Calendar] -> [14 - Wait 4 Days]
[14 - Wait 4 Days] -> [15 - Email: Last Note From Us]
[15 - Email: Last Note From Us] -> [16 - Goal: They Replied or Booked]
[16 - Goal: They Replied or Booked] -> [17 - Remove the sales-request Tag]
[17 - Remove the sales-request Tag] -> [18 - Move the Request to Replied]
[18 - Move the Request to Replied] -> [19 - Text You That They Answered]
