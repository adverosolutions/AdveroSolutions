# Their 3 application questions (reference only; skill rule 9: not answered point by point in the proposal. Fill every [LORENZO] if Upwork shows a text box)

**1. How do you recommend capturing Shopify line-item properties and sending them to HubSpot Line Items or Deals without using the native integration?**
Point Shopify's orders/create and orders/updated webhooks at a Make scenario, then make one Admin GraphQL call for each line item's properties and the product metafields, since the webhook doesn't carry metafields. The scenario searches HubSpot deals for the Shopify order ID, upserts the contact by email, creates the deal tied to that contact, and writes each line item with its options as custom line item properties associated to the deal. A unique-value shopify_order_id property on the deal backs up the search when two webhooks arrive at once.

**2. Briefly describe a past project where you integrated Shopify advanced product options or metafields with HubSpot.**
I haven't done a Shopify-options-to-HubSpot project before, so I built the core of yours for this application: the Make scenario in my video pulls line-item properties and metafields from a Shopify order and writes them to HubSpot Contacts, Deals and Line Items without duplicates. I build in Make daily. [LORENZO: add a Shopify or HubSpot project here only if you have a real one.]

**3. What is your preferred tool for this setup (e.g., Shopify Flow, Make/Zapier, or custom HubSpot Private App), and why?**
Make, calling HubSpot's CRM API with a private app token. This sync is a chain of calls that depend on each other (find the deal, upsert the contact, create the deal, loop the line items), and Make runs that chain with every run visible and replayable and no server for you to host. If order volume ever outgrows Make's pricing, the same HubSpot calls move into a custom private app.

