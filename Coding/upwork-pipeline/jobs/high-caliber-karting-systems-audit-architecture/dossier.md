# Dossier - Business Systems & AI Automation Engineer - Audit, Integrate & Automate Multi-System Venue

url: https://www.upwork.com/jobs/~022102823830325550248

## Who they are
- First name: unknown (no `client first name:` line in the metadata, post not signed)
- Company: High Caliber Karting & Entertainment (named in the post; the title and spec use "High Caliber Karting", as their domain does)
- Industry: indoor karting and entertainment venue ("our entertainment venue"), with booking, POS, a bar and bistro, events and physical venue controls
- Location / timezone: Michigan (US), America/New_York. Website: Okemos, MI (Lansing area)
- Website read: www.highcaliberkarting.com (home, /pricing/, /parties-events/), read-only.
  - Attractions: "Speed Track" and "Drift Track" (electric go karts), axe throwing, rage room, "The Battle Field" (gellyball / archery tag), throwbowling, pocket soccer, arcade, "Bar & Bistro" (full-service bar and restaurant).
  - Packages: "All Access Pass", "Thrills to Kill", birthday packages, corporate events, field trips and lock-ins. Pricing page says there is "no expiration on race credits".
  - Booking: "Book an Activity" / "Book Online" go to shop.bmileisure.com/highcaliberkarting/products, so BMI Leisure is their online shop. The /pricing/ page on the WordPress site lists the same activity prices, and every price links out to the BMI shop: prices live in two places.
  - Events: "High Caliber Event Request Form" on the site. Fields: Name, Company Name, Phone, Email, Party Type, Event description, Event Date and Time, Entertainment Options, Event Space Options, Event Duration, Total Attendees, Food & Beverage, Special Requests, "How did you hear about us?", reservation process acknowledgment. The form tool behind it is not visible (not confirmed as Jotform, HubSpot or Elementor).
  - Rooms: Executive VIP Room, Lamborghini Lounge, Trackside VIP room, Bar Side VIP room, Banquet Space, Flex Space, entire facility rental.
  - Their rule: "Events are only considered 'reserved' once a contract is executed and a deposit is received." That is a human-controlled step.
  - Website numbers (activity prices, room capacities, square footage) are NOT in the post, so none of them goes on the build or into a beat. Terminology only.

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
In order: BMI Leisure, Toast, HubSpot, WordPress/Elementor, Stripe, PayPal, QuickBooks, Deputy, MaintainX, Twilio, Jotform, Ubiquiti/UniFi, Google Admin, "several lighting and facility-control applications".
Tools they named as candidate approaches: n8n, Make, custom code, browser automation, AI agents; technologies: REST APIs, webhooks, Python, JavaScript/TypeScript, databases, AI integrations. "not a simple Zapier setup" (Zapier named only to rule it out).

## Every number in the post
- "dozens of platforms"
- "approximately 10-20 hours" for "the initial engagement", "a paid technology stack audit and automation architecture project"
- 13 platforms named in the stack sentence (counted from the post), plus "several lighting and facility-control applications"
- 13 categories named: POS, online booking, website, CRM, payments, staff management, maintenance, marketing, communications, networking, security, reporting, physical venue controls (counted)
- 10 "first responsibilities" (counted)
- 6 "thinks in terms of" questions (counted)
- 6 verdicts: "retained, integrated, automated, consolidated, replaced, or supplemented with custom software"
- Metadata: Hourly $35-$75, part time, expert. 1 contract (Personal/Executive Assistant, active since 2024-02, 3,204 hours), $67.3k spent, no feedback yet. 3 invites sent, 2 invited to interview, 0 hired, 0 offers. Bids avg $46.17, range $12-$100. 20 connects.
Missing numbers they obviously have (full platform count, who owns each login, which QuickBooks edition, which payments run through which processor, event volume) go to "Ask before quoting" and are never stated as fact.

## Their requirements, verbatim, in their order
1. "Review and validate our current software and technology inventory"
2. "Understand how each platform is used operationally"
3. "Identify APIs, webhooks, native integrations, and other programmatic access"
4. "Determine where n8n, Make, custom code, browser automation, or AI agents are appropriate"
5. "Identify duplicate data entry and repetitive manual processes"
6. "Identify systems that should remain human-controlled"
7. "Map how information should flow between systems"
8. "Identify security, permissions, logging, retry, and failure-handling requirements"
9. "Recommend which systems should be retained, integrated, automated, consolidated, replaced, or supplemented with custom software"
10. "Develop a phased implementation roadmap based on value, complexity, and risk"

10 parts in the post, 5 bands on the chart, adjacent pairs grouped (each band note names its pair):
- parts 1 and 2 share band 1 (inventory, and how each platform is used)
- parts 3 and 4 share band 2 (programmatic access, and which tool belongs where)
- parts 5 and 6 share band 3 (duplicate entry, and what remains human-controlled)
- parts 7 and 8 share band 4 (information flow, and security / failure handling)
- parts 9 and 10 share band 5 (a verdict per system, and the phased roadmap)

Their six questions, verbatim, used on the chart:
- "What is the source of truth?" (step 7)
- "Why is this task being done manually?" (band 3 note)
- "Can these systems communicate directly?" (gate 4, verbatim)
- "What should happen when an automation fails?" (step 8)
- "Does AI actually belong in this workflow?" (band 2 note)
- "Should we integrate this system or eventually replace it?" (band 5 note)

## The odd ask only they would recognize
"we do not want custom software built simply because it can be built. We want the simplest, most reliable solution for each business problem." Plus "not primarily a chatbot project and not a simple Zapier setup" and "a builder and systems thinker, not just an advisor."
On screen: gate 4 and arm 4b ("Custom Code Only When It Is Simpler"), band 2 note ("Native first, custom only when it is the simplest reliable answer"). Beat 4: "native beats custom code".

## What their hiring history implies
One contract ever: a Personal/Executive Assistant, active since 2024-02, 3,204 hours, $67.3k. They hire for the long haul and keep people; no feedback yet because that contract is still running. That EA likely holds a lot of the operational knowledge and logins, so the audit should interview them. They are an owner-run venue buying technical architecture for the first time on Upwork, and they say "builder, not just an advisor": they will judge on a concrete map of their own stack plus a first thing built, not a strategy deck. Already talking to 2 people from 3 invites, so speed matters.

## Their likely data
One event request as it comes off their own form, traced through the stack by the audit (illustrative sample, not their data):

```json
{
  "form": "High Caliber Event Request Form",
  "first_name": "Dana",
  "last_name": "Kowalczyk",
  "company_name": "Cedar Street Insurance Group",
  "email": "dana.kowalczyk@cedarstreetins.com",
  "party_type": "Corporate Event",
  "event_date_time": "2026-11-13 18:00",
  "entertainment_options": ["Speed Track Racing", "Axe Throwing", "Rage Room"],
  "event_space": "Trackside VIP Room",
  "event_duration": "3 hours",
  "total_attendees": 42,
  "food_and_beverage": "Bar & Bistro appetizer buffet, drink tickets",
  "how_did_you_hear": "Google search"
}
```

## Sizing (setup / infrastructure / method jobs only)
The audit budget against their own stack:
- "approximately 10-20 hours" for "dozens of platforms".
- Just the 13 named platforms: 10 h / 13 = about 46 minutes each; 20 h / 13 = about 92 minutes each. The full inventory is "dozens", so the real per-platform time is lower still.
- Insight: an even split gives every platform under an hour and every platform a shallow look. The audit has to triage: go deep where bookings and money move (BMI Leisure, Toast, Stripe, PayPal, QuickBooks, HubSpot, WordPress/Elementor), inventory-only for the rest (Ubiquiti/UniFi, Google Admin, lighting and facility-control apps).
- Second insight (from their site): prices sit on the WordPress pricing page and in the BMI Leisure shop, so pricing is typed twice today; "pricing synchronization" is already on their own list of future work. Phase 1 candidate.
- Third: guest records likely exist in both BMI Leisure (every booking) and HubSpot (CRM); "What is the source of truth?" for guests is a decision they make, not one the audit can assume.
On the chart: step 1 (triage), step 5 and step 10 (pricing typed twice, Phase 1 candidate), step 7 (guests in BMI or HubSpot?). In beats 3, 5 and 7.

## Three things they would recognize on screen
1. Their six questions, verbatim: gate 4 "Can These Systems Communicate Directly?", step 7 source of truth, step 8 "When an Automation Fails", band notes 2, 3 and 5.
2. Every platform they named, by name: BMI Leisure, Toast, Deputy, MaintainX (step 2); Toast, BMI Leisure (step 3); Stripe, PayPal, QuickBooks, n8n, Make (step 4a); WordPress/Elementor, Jotform, HubSpot (step 5); UniFi, Google Admin, lighting (step 6a); HubSpot, QuickBooks (step 7); Twilio (step 8).
3. Their own venue from their site: prices on the WordPress pricing page vs the BMI shop (step 5), event deposits as human-controlled because "reserved" means contract plus deposit (step 6a), and the Event Request Form record with Speed Track, Trackside VIP Room and Bar & Bistro (samples).
Plus their numbers "dozens" and "10-20 hours" on step 1.

## Beat 1 draft
"High Caliber team, this is your technology stack audit and automation architecture." (first name unknown; company named)
