@direction LR
@spacing 60

(1 - Enquiry Arrives From the Website Form) -> [15 - Idempotency Key: Hash of Email Phone and Timestamp, Skip if Seen]
[15 - Idempotency Key: Hash of Email Phone and Timestamp, Skip if Seen] -> [2 - Standardize Name, Phone E.164, Email Lowercase]
[2 - Standardize Name, Phone E.164, Email Lowercase] -> {3 - Required Fields Present?}
{3 - Required Fields Present?} -> "false" -> [3b - GHL: Tag Incomplete and Ask for the Missing Field]
{3 - Required Fields Present?} -> "true" -> [4 - GHL: Look Up Existing Contact by Email or Phone]
[4 - GHL: Look Up Existing Contact by Email or Phone] -> {5 - Already Exists?}
{5 - Already Exists?} -> "true" -> [6 - Extract Service, Summarize, Classify Hot Warm Cold Unclear]
{5 - Already Exists?} -> "false" -> [6 - Extract Service, Summarize, Classify Hot Warm Cold Unclear]
[6 - Extract Service, Summarize, Classify Hot Warm Cold Unclear] -> {7 - Clear Enough to Qualify?}
{7 - Clear Enough to Qualify?} -> "false" -> [7b - Manual Review Queue With the Summary]
{7 - Clear Enough to Qualify?} -> "true" -> [8 - GHL: Create or Update the Contact and Custom Fields]
[8 - GHL: Create or Update the Contact and Custom Fields] -> [9 - GHL: Tag by Class]
[9 - GHL: Tag by Class] -> [10 - GHL: Create or Move the Opportunity to the Stage]
[10 - GHL: Create or Move the Opportunity to the Stage] -> [11 - GHL: Write the Summary and Result to the Contact Notes]
[11 - GHL: Write the Summary and Result to the Contact Notes] -> [12 - GHL: Enroll in the Follow-Up Workflow With the Booking Link]
[12 - GHL: Enroll in the Follow-Up Workflow With the Booking Link] -> [[16 - Execution Log Row]]
(13 - GHL: Replied, Booked, Opted Out or Paused) -> [14 - GHL: Remove From the Follow-Up Workflow]
(17 - Any Step Fails) -> [18 - Retry After 2 Minutes]
[18 - Retry After 2 Minutes] -> [19 - Alert After the Retry]
[Claude] --> [6 - Extract Service, Summarize, Classify Hot Warm Cold Unclear]
[Service, Summary, Class, Missing Fields] --> [6 - Extract Service, Summarize, Classify Hot Warm Cold Unclear]
