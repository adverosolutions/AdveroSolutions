@direction LR
@spacing 60

(1 - Shopify Order Created or Updated: Webhook Fires) -> [2 - Shopify: Pull Line-Item Properties and Metafields]
[2 - Shopify: Pull Line-Item Properties and Metafields] -> [3 - HubSpot: Search Deals for This Shopify Order ID]
[3 - HubSpot: Search Deals for This Shopify Order ID] -> {4 - New Order or Already a Deal?}
{4 - New Order or Already a Deal?} -> "New Order" -> [4a - HubSpot: Upsert the Contact by Email]
{4 - New Order or Already a Deal?} -> "Already Synced" -> [4b - HubSpot: Update That Deal's Amount and Status]
[4a - HubSpot: Upsert the Contact by Email] -> [5 - HubSpot: Create the Deal With Its Options]
[5 - HubSpot: Create the Deal With Its Options] -> [6 - Shopify: Save the HubSpot Deal ID on the Order]
[6 - Shopify: Save the HubSpot Deal ID on the Order] -> [7 - Split the Order Into Its Line Items]
[7 - Split the Order Into Its Line Items] -> [8 - HubSpot: Create Each Line Item With Its Options]
(9 - Shopify Checkout Created or Updated: Webhook Fires) -> [10 - HubSpot: Save the Cart's Options and Recovery Link on the Contact]
