# Beats - AI Agent for Your Existing Database

- This is an AI agent that works inside your existing database.
- Step one: you ask in plain English, like which orders are pending.
- Claude searches your tables and answers with the row IDs.
- Search tool is read-only, so a question never changes a row.
- Updates wait for your yes: old value, new value, then you approve.
- Write access is the risk: no deletes, allowed columns, everything logged.
- Built on Postgres; if you're on MySQL, it swaps on our call.
- Can start [START], working demo by [DRAFT].
