@direction LR
@spacing 60

(1 - Faire Wholesale Order) -> [2 - Normalize: SKUs, Quantities, Customer, Channel]
(1b - Shopify Order) -> [2 - Normalize: SKUs, Quantities, Customer, Channel]
[2 - Normalize: SKUs, Quantities, Customer, Channel] -> {3 - Every SKU Exists in Unleashed?}
{3 - Every SKU Exists in Unleashed?} -> "true" -> [4 - Unleashed: Create the Sales Order and Allocate Stock]
{3 - Every SKU Exists in Unleashed?} -> "false" -> [3b - Alert: Unmapped SKU, Order Parked]
[4 - Unleashed: Create the Sales Order and Allocate Stock] -> {5 - Unleashed Accepted It?}
{5 - Unleashed Accepted It?} -> "true" -> [6 - Xero: Create the Invoice Against the Right Contact]
{5 - Unleashed Accepted It?} -> "false" -> [5b - Back Off 60 Seconds and Retry]
[5b - Back Off 60 Seconds and Retry] --> [4 - Unleashed: Create the Sales Order and Allocate Stock]
[6 - Xero: Create the Invoice Against the Right Contact] -> {7 - Xero Accepted It?}
{7 - Xero Accepted It?} -> "true" -> [8 - Shopify or Faire: Write Back Fulfilment and Invoice Number]
{7 - Xero Accepted It?} -> "false" -> [[7b - Dead Letter: Order, Error, Payload, for Replay]]
[8 - Shopify or Faire: Write Back Fulfilment and Invoice Number] -> [[9 - Run Log: Order, Channel, Each Step, Duration]]
[[7b - Dead Letter: Order, Error, Payload, for Replay]] -> [[9 - Run Log: Order, Channel, Each Step, Duration]]
[[9 - Run Log: Order, Channel, Each Step, Duration]] -> [[11 - Read Yesterday's Runs and Dead Letters]]
(10 - Every Morning at 7am) -> [[11 - Read Yesterday's Runs and Dead Letters]]
[[11 - Read Yesterday's Runs and Dead Letters]] -> [12 - Health Check: Orders In, Invoiced, Parked, Failed]
[12 - Health Check: Orders In, Invoiced, Parked, Failed] -> [13 - Post the Health Report, Green or Red]
(14 - Any Node Fails, Any Workflow) -> [15 - Alert With Workflow, Node, Order Id]
