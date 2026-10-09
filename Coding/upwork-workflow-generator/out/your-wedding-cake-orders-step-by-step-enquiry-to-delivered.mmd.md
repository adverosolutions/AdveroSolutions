# Your Wedding Cake Orders, Step by Step: Enquiry to Delivered

```mermaid
flowchart LR
    subgraph sec_enquiry["1 - A COUPLE ENQUIRES"]
        direction TB
        enquire["1 - A couple sends an enquiry, and it lands on your Monday consultations board"]
        reply["2 - They get an email right away with a link to book a tasting"]
    end
    subgraph sec_consult["2 - CONSULTATION: TASTING, DESIGN, DEPOSIT"]
        direction TB
        tasting["3 - They book a tasting in Square, and Zapier adds the date to their Monday item"]
        design["4 - After the tasting, you add the design, tiers, flavors and servings"]
        deposit["5 - They pay the deposit in Square, and Zapier marks them Booked in Monday"]
        nudge["6 - No deposit yet? Monday reminds you to follow up with them"]
    end
    subgraph sec_delivery["3 - DELIVERY DAY AND AFTER"]
        direction TB
        move["7 - Booked cakes move to your deliveries board with the venue and setup time"]
        balance["8 - Before your due date, Monday checks the final balance came in through Square"]
        daylist["9 - On the day, your driver sees the delivery list in the Monday app"]
        photo["10 - At the venue, a setup photo goes on the item and it's marked Delivered"]
        review["11 - After the wedding, the couple gets a thank-you email asking for a review"]
    end
    enquire --> reply
    reply --> tasting
    tasting --> design
    design --> deposit
    deposit --> nudge
    nudge --> move
    move --> balance
    balance --> daylist
    daylist --> photo
    photo --> review
    style sec_enquiry fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_consult fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_delivery fill:#ede9fe,stroke:#94a3b8,color:#0f172a
```

- **1 - A COUPLE ENQUIRES** - Every enquiry lands in Monday on its own, and the couple hears back right away.
- **2 - CONSULTATION: TASTING, DESIGN, DEPOSIT** - Your consultations in Monday: Zapier moves each couple along as they book and pay in Square.
- **3 - DELIVERY DAY AND AFTER** - Your deliveries in Monday: the balance, the day's list and the photo at the venue, then a thank-you.
