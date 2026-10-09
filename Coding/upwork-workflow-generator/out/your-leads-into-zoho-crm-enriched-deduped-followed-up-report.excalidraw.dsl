@direction LR
@spacing 60

(1 - New Lead From Your Ads or Website Form) -> [2 - Apollo: Enrich With Job Title, Company and Website]
[2 - Apollo: Enrich With Job Title, Company and Website] -> [3 - Zoho CRM: Match by Email or Phone, Then Create or Update]
[3 - Zoho CRM: Match by Email or Phone, Then Create or Update] -> {4 - New to Zoho CRM?}
{4 - New to Zoho CRM?} -> "true" -> [5 - Gmail: Send Email 1 Within a Minute]
[5 - Gmail: Send Email 1 Within a Minute] -> [6 - Wait 1 Day]
[6 - Wait 1 Day] -> [7 - Zoho CRM: Check the Lead Status]
[7 - Zoho CRM: Check the Lead Status] -> {8 - Not Contacted Yet and Has a Phone?}
{8 - Not Contacted Yet and Has a Phone?} -> "true" -> [9 - Twilio: Send the Next-Day Text]
(10 - Every Monday Morning) -> [11 - Zoho CRM: Pull Leads, Converted Ones Included]
[11 - Zoho CRM: Pull Leads, Converted Ones Included] -> [12 - Count Leads and Conversions by Source]
[12 - Count Leads and Conversions by Source] -> [[13 - Google Sheets: Refresh Your Lead Dashboard]]
