# Dossier - AI Automation & Agent Developer

url: https://www.upwork.com/jobs/~022104585966712066767

## Who they are
- First name: unknown
- Company: unknown
- Industry: unknown. The post says only "our business" and "our team". No product, service or customer type is named.
- Location / timezone: Nigeria (metadata only; never on screen)
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
None. Committed to the most common stack for this kind of role: n8n for the workflows and Claude for the agent, with a Postgres orders/accounts database as the lookup source. Named once, quietly, in the prototype's rail footer ("Runs on n8n + Claude"), not as a claim about their stack.

## Every number in the post
- "Hourly $10-$40" (metadata rate)
- "FULL TIME" (metadata; pitch as a retainer)
- "1 invite", "Recorded bids avg $28.10" (metadata)
- The post body itself contains no numbers. Every number in the prototype (hours saved, runs, success rate) is labelled illustrative.

## Their requirements, verbatim, in their order
1. "build and optimize AI-powered automation workflows for our business"
2. "designing end-to-end processes"
3. "improving existing systems"
4. "creating reliable agent-based solutions that reduce manual work"
5. "collaborate with our team to identify automation opportunities"
6. "implement practical workflows"
7. "ensure systems run smoothly over time"
8. "communicate clearly and deliver dependable results"

8 parts in the post, 5 screens in the prototype:
- Overview: part 1 (the whole operating layer) and part 8 (the weekly report is the "communicate clearly" artifact, linked from here).
- "End-to-end agent workflow": parts 2 and 4 (one end-to-end process run by an agent with real tools).
- "Improving existing systems": part 3.
- "Automation opportunities": parts 5 and 6 (the discovery ranking and which ones are live / building / next).
- "Runs smoothly over time": parts 7 and 8 (reliability, alerts, weekly report).

## The odd ask only they would recognize
"ensure systems run smoothly over time" together with "dependable results": most posts stop at "build". This one asks for the after-care, so the reliability screen and the before/after of a flaky workflow carry as much weight as the agent itself.

## What their hiring history implies
Not pulled. One invite, fresh post, wide rate range ($10-$40): likely a small team that has some automations already ("improving existing systems") and wants one dependable person on it full time. They will judge on whether the work looks dependable and clearly explained, not on novelty.

## Their likely data
Unknown business, so the sample stays generic to any business that takes customer requests and orders (the Direction's example): a customer request, an order, an account.

```json
{ "request_id": "REQ-2291", "channel": "email", "from": "Daniel Reyes", "subject": "Where is my order #10482?", "order_id": "10482", "order_status": "Dispatched 26 Sep, expected 30 Sep", "account": "customer since 2024, 7 orders, no open tickets", "outcome": "reply sent, ticket closed", "handled_in_s": 38 }
```

## Sizing (setup / infrastructure / method jobs only)
Not a setup job and the post gives no volumes. The opportunity map ranks processes by manual hours per week and totals them (38.5 h/week, illustrative). The real figure comes from the first discovery session; that is the first thing to ask.

## Three things they would recognize on screen
1. "reduce manual work": the opportunity map is ranked by hours of manual work per week, with a total at the top (Automation opportunities screen, and the Overview).
2. "reliable agent-based solutions": the agent trace shows each tool call (look up order, check account, update record) and a confidence gate that hands anything unsure to a person (End-to-end agent workflow screen).
3. "improving existing systems" / "run smoothly over time": the Replay-a-failure before/after and the Runs smoothly screen with alerts and the Monday weekly report.

## Beat 1 draft
"This is your automation operations center, a working prototype for your team."
