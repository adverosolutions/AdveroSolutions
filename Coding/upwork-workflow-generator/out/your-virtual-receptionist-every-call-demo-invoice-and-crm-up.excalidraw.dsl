@direction LR
@spacing 60

(1 - Retell Answers Your Line and Sends the Caller's Number) -> [2 - HubSpot: Look Up the Caller by Phone Number]
[2 - HubSpot: Look Up the Caller by Phone Number] -> [3 - Greet Them by Name in English or Spanish]
(4 - Caller Asks About a Machine) -> [[5 - Read Your Inventory List, Live]]
[[5 - Read Your Inventory List, Live]] -> [6 - Answer From Your Inventory Only, in Their Language]
(7 - Caller Wants to See It in Person) -> [8 - Book the Look or Demo on Your Facility Calendar]
[8 - Book the Look or Demo on Your Facility Calendar] -> [9 - Text Them the Time, the Machine and Your Address]
(10 - Tell It Who Bought Which Machine) -> [11 - QuickBooks: Create the Invoice for the Machine]
[11 - QuickBooks: Create the Invoice for the Machine] -> [12 - QuickBooks: Email the Invoice to the Buyer]
(13 - Call Ends: Retell Sends the Transcript) -> [14 - Keep Only Finished Calls With a Transcript]
[14 - Keep Only Finished Calls With a Transcript] -> [15 - Write the CRM Note in English, Even From a Spanish Call]
[15 - Write the CRM Note in English, Even From a Spanish Call] -> [16 - HubSpot: Save the Caller, the Machine and the Next Step]
(17 - Any Step Fails) -> [18 - Email You the Step That Broke]
[Claude - Answers From Your Inventory] --> [6 - Answer From Your Inventory Only, in Their Language]
[Claude - Writes the English CRM Note] --> [15 - Write the CRM Note in English, Even From a Spanish Call]
[CRM Fields: Caller, Machine, Next Step, Note] --> [15 - Write the CRM Note in English, Even From a Spanish Call]
