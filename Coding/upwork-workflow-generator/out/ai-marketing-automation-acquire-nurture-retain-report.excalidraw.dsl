@direction LR
@spacing 60

(1 · New Lead or Customer Event Arrives) -> [2 · Normalize Source, Stage, and Last Activity]
[2 · Normalize Source, Stage, and Last Activity] -> [3 · Claude Segments and Picks the Next Best Message]
[3 · Claude Segments and Picks the Next Best Message] -> {4 · Route by Journey: Acquisition, Nurture, Retention}
{4 · Route by Journey: Acquisition, Nurture, Retention} -> "Acquisition" -> [5 · Send the Welcome and First Offer Email]
{4 · Route by Journey: Acquisition, Nurture, Retention} -> "Nurture" -> [6 · Wait Two Days Before the Next Touch]
{4 · Route by Journey: Acquisition, Nurture, Retention} -> "Retention" -> {10 · Quiet for 30 Days or More?}
[5 · Send the Welcome and First Offer Email] -> [12 · Update CRM Stage and Tags]
[6 · Wait Two Days Before the Next Touch] -> [7 · Claude Writes the Personalized Nurture Touch]
[7 · Claude Writes the Personalized Nurture Touch] -> [8 · Send the Nurture Email]
[8 · Send the Nurture Email] -> {9 · Did They Open or Click It?}
{9 · Did They Open or Click It?} -> "true" -> [12 · Update CRM Stage and Tags]
{9 · Did They Open or Click It?} --> [6 · Wait Two Days Before the Next Touch]
{10 · Quiet for 30 Days or More?} -> "true" -> [11 · Send the Win Back Campaign]
{10 · Quiet for 30 Days or More?} -> "false" -> [12 · Update CRM Stage and Tags]
[11 · Send the Win Back Campaign] -> [12 · Update CRM Stage and Tags]
[12 · Update CRM Stage and Tags] -> [[13 · Log a Campaign Metrics Row]]
(14 · Every Monday Morning) -> [15 · Roll Up Opens, Clicks, and Conversions]
[15 · Roll Up Opens, Clicks, and Conversions] -> [16 · Post the Weekly Performance Digest]
(17 · Any Step Fails, Anywhere) -> [18 · Alert With a Link to the Failed Run]
[Claude] --> [3 · Claude Segments and Picks the Next Best Message]
[CRM Lookup: Past Opens, Purchases, and Stage] --> [3 · Claude Segments and Picks the Next Best Message]
[Force Segment, Campaign, Channel, and Send Time] --> [3 · Claude Segments and Picks the Next Best Message]
