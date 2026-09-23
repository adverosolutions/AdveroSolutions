@direction LR
@spacing 60

(New Purchase or Subscription Started) -> [Normalize Customer, Plan, Tier, and Payment Terms]
[Normalize Customer, Plan, Tier, and Payment Terms] -> [Grant Membership Access and Tag the Tier]
[Grant Membership Access and Tag the Tier] -> [Add to the Onboarding Email and SMS Flow]
[Add to the Onboarding Email and SMS Flow] -> [[Log Every Event: What Fired, What Tagged, What Charged]]
(Recurring Payment Succeeded or Failed) -> {Did the Payment Fail?}
{Did the Payment Fail?} -> "false" -> [Extend Access and Update the Renewal Date]
{Did the Payment Fail?} -> "true" -> [Start Dunning: Retry Notice by Email and SMS]
[Start Dunning: Retry Notice by Email and SMS] -> [Wait 3 Days for a Payment Update]
[Wait 3 Days for a Payment Update] -> {Still Unpaid After 3 Days?}
{Still Unpaid After 3 Days?} -> "true" -> [Pause Access and Tag At-Risk]
{Still Unpaid After 3 Days?} -> "false" -> [Mark Recovered and Clear the At-Risk Tag]
[Extend Access and Update the Renewal Date] -> [[Log Every Event: What Fired, What Tagged, What Charged]]
[Pause Access and Tag At-Risk] -> [[Log Every Event: What Fired, What Tagged, What Charged]]
[Mark Recovered and Clear the At-Risk Tag] -> [[Log Every Event: What Fired, What Tagged, What Charged]]
(Cancellation Requested) -> [Revoke Access at Period End and Tag Churned]
[Revoke Access at Period End and Tag Churned] -> [Start the Win-Back Sequence]
[Start the Win-Back Sequence] -> [[Log Every Event: What Fired, What Tagged, What Charged]]
[[Log Every Event: What Fired, What Tagged, What Charged]] -> {Did Anything Fail to Fire, Tag, or Charge?}
{Did Anything Fail to Fire, Tag, or Charge?} -> "true" -> [Alert With the Customer, the Step, and Why]
{Did Anything Fail to Fire, Tag, or Charge?} -> "false" -> [All Clean]
