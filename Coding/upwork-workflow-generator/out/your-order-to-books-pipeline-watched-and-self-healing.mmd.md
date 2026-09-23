# Your Order to Books Pipeline, Watched and Self-Healing

```mermaid
flowchart LR
    subgraph sec_intake["1 - AN ORDER COMES IN FROM EITHER CHANNEL"]
        direction TB
        faire(["1 - Faire Wholesale Order"])
        shopify(["1b - Shopify Order"])
        normalize["2 - Normalize: SKUs, Quantities, Customer, Channel"]
    end
    subgraph sec_breaks["2 - THE THREE PLACES IT USUALLY BREAKS"]
        direction TB
        skugate{"3 - Every SKU Exists in Unleashed?"}
        unmapped["3b - Alert: Unmapped SKU, Order Parked<br/><i>slack</i>"]
        unleashed["4 - Unleashed: Create the Sales Order and Allocate Stock"]
        unleashedgate{"5 - Unleashed Accepted It?"}
        backoff["5b - Back Off 60 Seconds and Retry"]
        xero["6 - Xero: Create the Invoice Against the Right Contact"]
        xerogate{"7 - Xero Accepted It?"}
        deadletter[("7b - Dead Letter: Order, Error, Payload, for Replay<br/><i>googleSheets</i>")]
    end
    subgraph sec_closeloop["3 - CLOSE THE LOOP"]
        direction TB
        writeback["8 - Shopify or Faire: Write Back Fulfilment and Invoice Number"]
        runlog[("9 - Run Log: Order, Channel, Each Step, Duration<br/><i>googleSheets</i>")]
    end
    subgraph sec_health["4 - EVERY MORNING, PROVE IT IS HEALTHY"]
        direction TB
        sched(["10 - Every Morning at 7am"])
        readlog[("11 - Read Yesterday's Runs and Dead Letters<br/><i>googleSheets</i>")]
        healthcheck["12 - Health Check: Orders In, Invoiced, Parked, Failed"]
        report["13 - Post the Health Report, Green or Red<br/><i>slack</i>"]
    end
    subgraph sec_loud["5 - NOTHING FAILS QUIETLY"]
        direction TB
        err(["14 - Any Node Fails, Any Workflow<br/><i>n8n</i>"])
        alert["15 - Alert With Workflow, Node, Order Id<br/><i>slack</i>"]
    end
    faire --> normalize
    shopify --> normalize
    normalize --> skugate
    skugate -->|true| unleashed
    skugate -->|false| unmapped
    unleashed --> unleashedgate
    unleashedgate -->|true| xero
    unleashedgate -->|false| backoff
    backoff -.-> unleashed
    xero --> xerogate
    xerogate -->|true| writeback
    xerogate -->|false| deadletter
    writeback --> runlog
    deadletter --> runlog
    runlog --> readlog
    sched --> readlog
    readlog --> healthcheck
    healthcheck --> report
    err --> alert
    style sec_intake fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_breaks fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_closeloop fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_health fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_loud fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 - AN ORDER COMES IN FROM EITHER CHANNEL** - Faire wholesale and Shopify DTC land on separate hooks and get flattened into one shape, so every downstream step reads the same fields no matter which channel sent it.
- **2 - THE THREE PLACES IT USUALLY BREAKS** - An unmapped SKU, an Unleashed call that times out or hits a rate limit, and a Xero call on an expired token. Each one gets a gate, and each gate has somewhere safe to put the order instead of dropping it.
- **3 - CLOSE THE LOOP** - The channel gets the fulfilment and invoice number written back, and every run leaves a row behind with timings, so a slow step is visible before it becomes a broken one.
- **4 - EVERY MORNING, PROVE IT IS HEALTHY** - A 7am pass over yesterday's log and dead letters, counted and posted. Green means the numbers reconcile. Red names the orders that need a human before anyone has to ask.
- **5 - NOTHING FAILS QUIETLY** - One error trigger covers every workflow in the instance, so a breakdown announces itself with the workflow, the node and the order id instead of being found days later in a stock count.
