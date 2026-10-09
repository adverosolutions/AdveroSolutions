# Dossier - Fix & Optimize n8n Webhook Workflow

url: https://www.upwork.com/jobs/~022104589162872584802

## Who they are
- First name: unknown
- Company: unknown
- Industry: unknown. They run an existing n8n workflow that receives data on an HTTP Webhook and passes it to a downstream API.
- Location / timezone: client location not shown
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
1. n8n
2. HTTP Webhook (n8n Webhook trigger)
3. Code/Set node
4. "the downstream API target" (unnamed; the prototype calls it `POST /v1/orders` on "your downstream API", labelled as sample)

## Every number in the post
- "Fixed $60", expert level
- "Recorded bids avg $55.64"
- Posted 2026-09-28
- No volumes, no payload size, no API name, no error text in the post.

## Their requirements, verbatim, in their order
1. "inspect the workflow export"
2. "resolve the JSON mapping errors in the Code/Set node"
3. "ensure smooth data delivery to the downstream API target"

3 parts in your post; the prototype has a Run overview, one screen per part (Inspect the export, Fix the mapping, Deliver to the API), plus Test payloads and the "what was wrong" note. The last two are the proof the fix holds, not extra scope.

## The odd ask only they would recognize
"failing during the payload transformation step" in a "Code/Set node": they know where it breaks, not why. The prototype stops at that exact node with the exact kind of error n8n prints there, then shows the broken lines.

## What their hiring history implies
Client record not pulled. A $60 fixed fix at expert level with bids clustered near $55 reads as a buyer who wants it working today, judged on one thing: executions going green and the API receiving data. No strategy deck.

## Their likely data
The post gives no payload. Sample used on screen (labelled illustrative): an order-created event whose sender nests the record under `body.data`, with strings where the API wants numbers.

```json
{ "body": { "event": "order.created", "data": { "order_id": "ORD-20488", "created_at": "09/28/2026 14:03",
  "contact": { "first_name": "Dana", "last_name": "Whitfield", "email": "Dana.Whitfield@example.com " },
  "items": [ { "sku": "KIT-204", "qty": "2", "price": "49.50" }, { "sku": "SVC-011", "qty": "1", "price": "50.00" } ],
  "total": "149.00", "currency": "usd" } } }
```

## Sizing
Not a setup job. The fix is one Code node rewrite, one new validation node, retry settings on the HTTP node and one error branch.

## Three things they would recognize on screen
1. Their Code/Set node failing on the payload transformation step: Run screen, node "Transform payload", red error "Cannot read properties of undefined (reading 'email') [line 4]".
2. Their workflow export: "Inspect the export" screen, the nodes as the export lists them, findings pinned to node and line.
3. Their downstream API target: "Deliver to the API" screen, schema check and the POST returning 200.

## Beat 1 draft
"This is your webhook workflow fixed, delivering cleanly to your downstream API."
