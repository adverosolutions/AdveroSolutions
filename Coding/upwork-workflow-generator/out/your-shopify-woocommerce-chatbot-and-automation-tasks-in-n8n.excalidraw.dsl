@direction LR
@spacing 60

(1 - Shopper Asks a Question in Your Store Chat) -> [2 - Claude Sorts It: Order Status, Product Question or a Person]
[2 - Claude Sorts It: Order Status, Product Question or a Person] -> {3 - Your Store: Shopify or WooCommerce?}
{3 - Your Store: Shopify or WooCommerce?} -> "Shopify" -> [4a - Shopify: Look Up the Order or the Product]
{3 - Your Store: Shopify or WooCommerce?} -> "WooCommerce" -> [4b - WooCommerce: Look Up the Order or the Product]
{3 - Your Store: Shopify or WooCommerce?} -> "No Lookup Needed" -> [5 - One Shape for Either Store, Email Must Match]
[4a - Shopify: Look Up the Order or the Product] -> [5 - One Shape for Either Store, Email Must Match]
[4b - WooCommerce: Look Up the Order or the Product] -> [5 - One Shape for Either Store, Email Must Match]
[5 - One Shape for Either Store, Email Must Match] -> [6 - Claude Writes the Reply From Your Live Store Data]
[6 - Claude Writes the Reply From Your Live Store Data] -> [7 - Send the Reply Back to the Shopper]
[7 - Send the Reply Back to the Shopper] -> {8 - Order Still Unshipped Past Your Shipping Promise?}
{8 - Order Still Unshipped Past Your Shipping Promise?} -> "true" -> [8b - Gmail: Flag the Late Order Before They Ask Again]
{8 - Order Still Unshipped Past Your Shipping Promise?} -> "false" -> [[9 - Google Sheets: Log Every Chat, Answer and Outcome]]
[8b - Gmail: Flag the Late Order Before They Ask Again] -> [[9 - Google Sheets: Log Every Chat, Answer and Outcome]]
[[9 - Google Sheets: Log Every Chat, Answer and Outcome]] -> {10 - Shopper Needs a Person?}
{10 - Shopper Needs a Person?} -> "true" -> [11 - Gmail: Hand the Chat to Your Support Inbox]
(12 - Any Step Fails, Anywhere) -> [13 - Gmail: Send You the Failed Step and a Run Link]
[Claude - Sorts Each Chat Message] --> [2 - Claude Sorts It: Order Status, Product Question or a Person]
[Memory - Keeps the Thread of This Chat] --> [2 - Claude Sorts It: Order Status, Product Question or a Person]
[Parser - Intent, Order Number, Email, Product] --> [2 - Claude Sorts It: Order Status, Product Question or a Person]
[Claude - Writes the Shopper Reply] --> [6 - Claude Writes the Reply From Your Live Store Data]
