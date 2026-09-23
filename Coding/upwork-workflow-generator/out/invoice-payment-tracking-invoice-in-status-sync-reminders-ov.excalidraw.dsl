@direction LR
@spacing 60

(New Invoice Created in the Accounting Tool) -> [Normalize Invoice: Customer, Amount, Due Date, Status]
[Normalize Invoice: Customer, Amount, Due Date, Status] -> [[Add the Invoice to the Tracking Sheet]]
(Payment Received from the Payment Tool) -> [Match the Payment to Its Invoice]
[Match the Payment to Its Invoice] -> [Mark the Invoice Paid in the Accounting Tool]
[Mark the Invoice Paid in the Accounting Tool] -> [[Update the Sheet: Status Paid, Date Paid]]
[[Update the Sheet: Status Paid, Date Paid]] -> [Notify the Team: Payment Received]
(Daily Check, 8am) -> [Find Unpaid Invoices Due in 3 Days, Due Today, or Past Due]
[Find Unpaid Invoices Due in 3 Days, Due Today, or Past Due] -> {Where Is It: Upcoming, Due Today, or Overdue?}
{Where Is It: Upcoming, Due Today, or Overdue?} -> "upcoming" -> [Send a Friendly Heads-Up: Due in 3 Days]
{Where Is It: Upcoming, Due Today, or Overdue?} -> "due today" -> [Send the Due-Today Reminder]
{Where Is It: Upcoming, Due Today, or Overdue?} -> "overdue" -> [Send the Overdue Notice]
[Send the Overdue Notice] -> [[Update the Sheet: Status Overdue, Days Late]]
[[Update the Sheet: Status Overdue, Days Late]] -> [Notify the Team: Invoice Overdue]
