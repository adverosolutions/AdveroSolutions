@direction LR
@spacing 60

(1 - New Lead From Your Website Form) -> [2 - Read the Enquiry and Write the First Reply]
[2 - Read the Enquiry and Write the First Reply] -> {3 - Is It a Real Enquiry?}
{3 - Is It a Real Enquiry?} -> "real enquiry" -> [4 - GoHighLevel: Create or Update the Contact]
{3 - Is It a Real Enquiry?} -> "spam or test entry" -> [3b - Spam or Test Entry: Stop, Nothing Sent]
[4 - GoHighLevel: Create or Update the Contact] -> {5 - Did GoHighLevel Save the Lead?}
{5 - Did GoHighLevel Save the Lead?} -> "saved" -> [6 - GoHighLevel: Save the Enquiry as a Note]
{5 - Did GoHighLevel Save the Lead?} -> "not saved" -> [5b - Email You the Lead and What Went Wrong]
[6 - GoHighLevel: Save the Enquiry as a Note] -> {7 - New Lead or Already in GoHighLevel?}
{7 - New Lead or Already in GoHighLevel?} -> "new lead" -> [8 - GoHighLevel: Add the Lead to Your Pipeline]
{7 - New Lead or Already in GoHighLevel?} -> "returning lead" -> [7b - GoHighLevel: Task for You to Call Them Back]
[8 - GoHighLevel: Add the Lead to Your Pipeline] -> [9 - GoHighLevel: Text the First Reply]
[9 - GoHighLevel: Text the First Reply] -> [10 - GoHighLevel: Start Your Follow-Up Sequence]
