@direction LR
@spacing 60

(New Lead or Inquiry Received) -> [Normalize Contact Info and Message]
[Normalize Contact Info and Message] -> [Check Dynamics CRM for an Existing Record]
[Check Dynamics CRM for an Existing Record] -> [Score the Lead, Classify Sales vs Support, and Draft a First Response]
[Score the Lead, Classify Sales vs Support, and Draft a First Response] -> [Create or Update the Record in Dynamics CRM]
[Create or Update the Record in Dynamics CRM] -> [Log the Interaction and Drafted Response as an Activity]
[Log the Interaction and Drafted Response as an Activity] -> {Classified as Sales-Ready or Support Request?}
{Classified as Sales-Ready or Support Request?} -> "true" -> [Notify Sales Rep: New Qualified Lead]
{Classified as Sales-Ready or Support Request?} -> "false" -> [Route to Support Queue for Review]
[Notify Sales Rep: New Qualified Lead] -> [Send the Drafted Response to the Contact]
[Route to Support Queue for Review] -> [Send the Drafted Response to the Contact]
[GPT-4.1] --> [Score the Lead, Classify Sales vs Support, and Draft a First Response]
