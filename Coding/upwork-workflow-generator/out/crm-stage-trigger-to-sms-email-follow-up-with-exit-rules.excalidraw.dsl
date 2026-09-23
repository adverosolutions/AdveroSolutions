@direction LR
@spacing 60

(1 · CRM Stage Changed · GoHighLevel / HubSpot) -> [2 · Normalize Contact, Stage, Consent and Touch Count]
[2 · Normalize Contact, Stage, Consent and Touch Count] -> {3 · Route by Pipeline Stage}
{3 · Route by Pipeline Stage} -> "New Lead" -> [4 · Instant SMS: Thanks, Quick Question]
{3 · Route by Pipeline Stage} -> "Proposal Sent" -> [12 · Proposal Sent: Delay Timer, Wait 2 Days]
{3 · Route by Pipeline Stage} -> "No Response" -> [14 · No Response: Breakup SMS, Should I Close Your File?]
[4 · Instant SMS: Thanks, Quick Question] -> [5 · Delay Timer: Wait 1 Hour]
[5 · Delay Timer: Wait 1 Hour] -> [6 · Email: Intro and Booking Link]
[6 · Email: Intro and Booking Link] -> [7 · Delay Timer: Wait 1 Day]
[7 · Delay Timer: Wait 1 Day] -> {8 · Replied or Booked? · Exit Rule}
{8 · Replied or Booked? · Exit Rule} -> "true" -> [9 · Stop Sequence: Lead Responded]
{8 · Replied or Booked? · Exit Rule} -> "false" -> {10 · Under 4 Touches? · Touch Cap}
{10 · Under 4 Touches? · Touch Cap} -> "true" -> [11 · Next SMS Touch, Then Back to the Day Timer]
{10 · Under 4 Touches? · Touch Cap} -> "false" -> [15 · Notify the Rep in Slack: Touch Sent or Sequence Ended]
[11 · Next SMS Touch, Then Back to the Day Timer] --> [7 · Delay Timer: Wait 1 Day]
[9 · Stop Sequence: Lead Responded] -> [15 · Notify the Rep in Slack: Touch Sent or Sequence Ended]
[12 · Proposal Sent: Delay Timer, Wait 2 Days] -> [13 · Email: Any Questions on the Proposal?]
[13 · Email: Any Questions on the Proposal?] -> [15 · Notify the Rep in Slack: Touch Sent or Sequence Ended]
[14 · No Response: Breakup SMS, Should I Close Your File?] -> [15 · Notify the Rep in Slack: Touch Sent or Sequence Ended]
[15 · Notify the Rep in Slack: Touch Sent or Sequence Ended] -> [16 · CRM: Update Contact Sequence Status]
(17 · Any Node Fails, Anywhere) -> [18 · Alert the Rep With a Link to the Failed Run]
