@direction LR
@spacing 60

[1 - Today: A Square Sale Becomes a Monday Item Through Zapier] -> [2 - Expanded: Zapier Finds the Couple's Item by Email, or Adds It]
[2 - Expanded: Zapier Finds the Couple's Item by Email, or Adds It] -> [3 - Consultations Board: Couple, Wedding Date, Venue, Tasting Date]
[3 - Consultations Board: Couple, Wedding Date, Venue, Tasting Date] -> [4 - After the Tasting: Design Details, Tiers, Flavors, Servings]
[4 - After the Tasting: Design Details, Tiers, Flavors, Servings] -> {5 - Deposit Paid in Square?}
{5 - Deposit Paid in Square?} -> "yes" -> [6 - Moves to Deliveries: Venue, Coordinator, Delivery and Setup Window]
{5 - Deposit Paid in Square?} -> "no" -> [5b - Not Yet: Monday Reminds You to Follow Up With the Couple]
[6 - Moves to Deliveries: Venue, Coordinator, Delivery and Setup Window] -> {7 - Final Balance Paid by Your Due Date?}
{7 - Final Balance Paid by Your Due Date?} -> "yes" -> [8 - This Week's Deliveries: One List by Date and Setup Window]
{7 - Final Balance Paid by Your Due Date?} -> "no" -> [7b - Not Yet: Monday Flags It to You Before the Cake Leaves]
[7b - Not Yet: Monday Flags It to You Before the Cake Leaves] -> [8 - This Week's Deliveries: One List by Date and Setup Window]
[8 - This Week's Deliveries: One List by Date and Setup Window] -> [9 - Delivered and Set Up: Venue Photo on the Item, Couple Done]
