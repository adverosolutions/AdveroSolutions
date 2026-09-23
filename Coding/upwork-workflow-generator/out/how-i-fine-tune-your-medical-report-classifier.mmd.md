# How I Fine Tune Your Medical Report Classifier

```mermaid
flowchart LR
    subgraph sec_clean["1 - CLEAN THE DATA"]
        direction TB
        clean["1 - Clean the 800 Reports, Send Suspect Labels Back to You"]
        split["2 - Set Aside a Test Set Before Anything Trains"]
    end
    subgraph sec_pick["2 - PICK A SMALL MODEL"]
        direction TB
        pick["3 - Pick a Small Open Source Model That Fits Your Categories"]
    end
    subgraph sec_train["3 - MEASURE, THEN TRAIN"]
        direction TB
        baseline["4 - Score the Untouched Model First"]
        train["5 - Train a Small Adapter on Your Examples"]
        gate{"6 - Does It Beat the Baseline, Especially on Urgent?"}
        fix["6a - Fix Labels, Rebalance, Train Again"]
    end
    subgraph sec_handoff["4 - PROVE IT AND HAND IT OVER"]
        direction TB
        handoff["7 - Adapter Files, One Command Script, Short Write Up"]
    end
    clean --> split
    split --> pick
    pick --> baseline
    baseline --> train
    train --> gate
    gate -->|false| fix
    fix -.-> train
    gate -->|true| handoff
    style sec_clean fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_pick fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_train fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_handoff fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
```

- **1 - CLEAN THE DATA** - Duplicates out, formatting fixed, suspicious labels sent back to you. A test set is set aside first so the results are honest.
- **2 - PICK A SMALL MODEL** - An existing lightweight open source model, not one built from scratch. Cheap to run, fast to train.
- **3 - MEASURE, THEN TRAIN** - Score the untouched model first so the before number is real. Then train a small adapter on your examples.
- **4 - PROVE IT AND HAND IT OVER** - Same test set, before vs after, per category. You get the adapter files, a one command script, and a short write up.
