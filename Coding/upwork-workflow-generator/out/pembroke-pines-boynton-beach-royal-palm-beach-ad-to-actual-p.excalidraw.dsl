@direction LR
@spacing 60

[1 - Your Own GHL Account, One Pipeline per Location, No Generic Snapshot] -> [2 - Every Lead Tagged: General Dental, Orthodontics, Invisalign or Braces]
[2 - Every Lead Tagged: General Dental, Orthodontics, Invisalign or Braces] -> [3 - Google Ads, Meta Ads, Website or Phone Call: Original Source Retained]
[3 - Google Ads, Meta Ads, Website or Phone Call: Original Source Retained] -> [4 - Tracking Numbers per Location Log Campaign, Source and Call Outcome]
[4 - Tracking Numbers per Location Log Campaign, Source and Call Outcome] -> {5 - Did the Caller or Form Lead Schedule?}
{5 - Did the Caller or Form Lead Schedule?} -> "yes" -> [6 - Google Ads Gets Scheduled, Showed, Became Patient, Treatment Started]
{5 - Did the Caller or Form Lead Schedule?} -> "no" -> [7 - Missed Call or Did Not Schedule: Text-Back, Then Follow-Up Until Booked]
[7 - Missed Call or Did Not Schedule: Text-Back, Then Follow-Up Until Booked] -> {8 - Status Changed Before the Next Message?}
{8 - Status Changed Before the Next Message?} -> "yes, booked" -> [10 - Confirmation and Reminders, No Show or Cancelled Moves to Rescheduled]
{8 - Status Changed Before the Next Message?} -> "never replied" -> [9 - Recall and Reactivation: Hygiene Due, Unscheduled Treatment, Orthodontic Consults]
[6 - Google Ads Gets Scheduled, Showed, Became Patient, Treatment Started] -> [10 - Confirmation and Reminders, No Show or Cancelled Moves to Rescheduled]
[9 - Recall and Reactivation: Hygiene Due, Unscheduled Treatment, Orthodontic Consults] -> "books" -> [10 - Confirmation and Reminders, No Show or Cancelled Moves to Rescheduled]
[10 - Confirmation and Reminders, No Show or Cancelled Moves to Rescheduled] -> [11 - Your PMS Moves the Stage: Showed, Became Patient, Treatment Started]
[11 - Your PMS Moves the Stage: Showed, Became Patient, Treatment Started] -> [12 - Dashboard: Show Rate and Lead-to-Patient Rate by Location and Campaign]
[12 - Dashboard: Show Rate and Lead-to-Patient Rate by Location and Campaign] -> [13 - Built So AI Calling Plugs In Later Without Rebuilding the CRM]
