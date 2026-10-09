# Square, Zapier and Monday: Wedding Cake Consultations and Deliveries

```mermaid
flowchart LR
    subgraph sec_basic["1 - YOUR VERY BASIC WORKFLOW SYSTEM, EXPANDED"]
        direction TB
        today["1 - Today: A Square Sale Becomes a Monday Item Through Zapier"]
        match["2 - Expanded: Zapier Finds the Couple's Item by Email, or Adds It"]
    end
    subgraph sec_consult["2 - CONSULTATIONS IN MONDAY"]
        direction TB
        consult_board["3 - Consultations Board: Couple, Wedding Date, Venue, Tasting Date"]
        design["4 - After the Tasting: Design Details, Tiers, Flavors, Servings"]
        deposit{"5 - Deposit Paid in Square?"}
        follow_up["5b - Not Yet: Monday Reminds You to Follow Up With the Couple"]
    end
    subgraph sec_deliver["3 - DELIVERIES IN MONDAY"]
        direction TB
        deliveries_board["6 - Moves to Deliveries: Venue, Coordinator, Delivery and Setup Window"]
        balance{"7 - Final Balance Paid by Your Due Date?"}
        balance_flag["7b - Not Yet: Monday Flags It to You Before the Cake Leaves"]
        week_list["8 - This Week's Deliveries: One List by Date and Setup Window"]
        delivered["9 - Delivered and Set Up: Venue Photo on the Item, Couple Done"]
    end
    today --> match
    match --> consult_board
    consult_board --> design
    design --> deposit
    deposit -->|yes| deliveries_board
    deposit -->|no| follow_up
    deliveries_board --> balance
    balance -->|yes| week_list
    balance -->|no| balance_flag
    balance_flag --> week_list
    week_list --> delivered
    style sec_basic fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_consult fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_deliver fill:#ede9fe,stroke:#94a3b8,color:#0f172a
```

- **1 - YOUR VERY BASIC WORKFLOW SYSTEM, EXPANDED** - Step 1 is my read of your Square, Zapier and Monday flow today, to confirm on our call. Expanded, every payment lands on the couple's one item, matched by the email on their Square invoice.
- **2 - CONSULTATIONS IN MONDAY** - Each couple from enquiry to tasting to design details on one board. The deposit landing in Square is what books them.
- **3 - DELIVERIES IN MONDAY** - Booked cakes move to Deliveries with the venue, the coordinator and your delivery and setup window. Monday checks the final balance against your due date.
