# Dossier - AI Automation Expert Needed for n8n and Shopify/WooCommerce Chatbots & Automation Tasks

url: https://www.upwork.com/jobs/~022102810572407798243

## Who they are
- First name: unknown (no `client first name:` line, post is unsigned)
- Company: unknown (no store name, no domain in the post)
- Industry: online store owner (or someone running stores) on "Shopify/WooCommerce"; which of the two is not given. Title says "Chatbots" plural, so possibly more than one store. Not asserted anywhere.
- Location / timezone: New York (US), timezone Etc/UTC
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
1. n8n
2. Shopify
3. WooCommerce ("Shopify/WooCommerce", platform choice not given)

Committed tools for the parts the post leaves open: Claude (Anthropic) for the chat brain, Gmail for the handoff and alerts, Google Sheets for the chat log. Reason: a small store owner who hires $5 to $30 gigs most likely runs on Gmail and Google Sheets; nothing in the post or history points to Slack or a helpdesk (Gorgias, Zendesk), so those are not assumed.

## Every number in the post
- "$30" fixed price (metadata), intermediate level
- "long-term opportunity" (no hours or months given)
- Hiring history: 8 contracts, 8 jobs with hires, 4 active, $38 spent in total, 5.0 over 4 reviews, 0 hours
- Bids: avg $113.96, range $15-$1,200; 0 invites, 0 interviewing, 0 hired
- Connects to apply: 11
- No business numbers at all: no order volume, chat volume, product count, shipping time, team size. On the build these are only labelled inputs (`PASTE-YOUR-DAYS-TO-SHIP`, `PASTE-YOUR-REPLY-TIME`) and they go under "Ask before quoting".

## Their requirements, verbatim, in their order
1. "Shopify/WooCommerce chatbot" (from "help with n8n and Shopify/WooCommerce chatbot and automation tasks")
2. "automation tasks"
3. "building and improving workflows"
4. "connecting systems"
5. "supporting ongoing automation needs"

5 parts in your post, 5 sections on the canvas:
- Section 1 = the chatbot (order status, product questions, either platform).
- Section 2 = the first automation task: a late, still-unshipped order gets flagged to them the moment a shopper asks about it.
- Section 3 = building and improving: every chat logged with the answer and outcome, which is what the improvements come from.
- Section 4 = connecting systems: chat to Gmail, the person-takes-over handoff with reply-to set to the shopper.
- Section 5 = supporting ongoing automation needs: the error path (any failed step emails them the step and a run link). This is their own part, so no extra error section follows it.

Soft asks (tone, not sections): "comfortable working independently, communicating clearly, and helping us solve automation challenges efficiently"; "contribute to chatbot and workflow development".

## The odd ask only they would recognize
The slash: "Shopify/WooCommerce", with no store named and no platform picked. The build answers it directly: one Config value (`store_platform`) and one switch, "3 - Your Store: Shopify or WooCommerce?", with a real Shopify Admin GraphQL call and a real WooCommerce REST call side by side, both flowing into one answer shape. Named in beat 2.

## What their hiring history implies
A very new, very high-volume hirer of tiny fixed jobs: 8 hires, $38 total (under $5 per job), all in the last week, across unrelated work (US medical billing, a YouTube movie-explainer editor, SMS marketing and cold outreach VA, a job application assistant, a Squarespace designer). Reads like someone assembling a bench of cheap specialists, possibly reselling work, and testing each with a small paid task. They judge on "does it work and did they communicate", not strategy. The $30 is a first task, not the budget for this build; "long-term" is the carrot. Price sensitivity is extreme, so the assessment prices the build honestly and puts the long-term work on a retainer.

## Their likely data
One shopper chat on a small home-goods store (illustrative: the store is not named, and the overview says so plainly), plus the order record the store returns.

```json
{
  "sessionId": "c7f2a9e4-5b1d-4f3e-9a2c-81d6e0b4f317",
  "action": "sendMessage",
  "chatInput": "Hi, I ordered 2 linen pillow covers on the 16th and still no shipping email. Order #1047, dana.whitfield@gmail.com. If it can't ship this week I'd rather cancel.",
  "store_order": {
    "name": "#1047",
    "email": "dana.whitfield@gmail.com",
    "createdAt": "2026-09-16T14:02:11Z",
    "displayFinancialStatus": "PAID",
    "displayFulfillmentStatus": "UNFULFILLED",
    "lineItems": [{"title": "Linen Pillow Cover - Sage", "quantity": 2}]
  }
}
```

## Sizing (setup / infrastructure / method jobs only)
Not a setup job, and the post gives no business numbers to size from. Anything volume-based (chats per month, Claude cost per month, n8n execution tier) is carried as their input and asked for in the assessment.

## Three things they would recognize on screen
1. Their slash, "Shopify/WooCommerce": the section 1 label, the switch "3 - Your Store: Shopify or WooCommerce?", the two lookups "4a - Shopify: ..." and "4b - WooCommerce: ...", and `store_platform` in "0 - Config: Your Settings".
2. Their own list of work, word for word and in order, as the section labels: "AUTOMATION TASK", "BUILDING AND IMPROVING WORKFLOWS", "CONNECTING SYSTEMS", "SUPPORTING ONGOING AUTOMATION NEEDS".
3. "Chatbot" doing the three things a store chatbot is hired for: order status, product questions, and a person taking over, on the node labels 2, 4a/4b and 11, with the overview sticky saying plainly the sample chat is made up because no store was named.

## Beat 1 draft
"This is your Shopify/WooCommerce chatbot and automation tasks for your store."
