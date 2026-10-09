# Dossier - Automation for Low Ticket Offer

url: https://www.upwork.com/jobs/~022104655571527050288

## Who they are
- First name: Sandro (the `client first name:` line, and he signs the post "Thanks Sandro")
- Company: Detox Nation (named in the post)
- Industry: "a wellness and coaching business"; he does "individual treatments" today and is building a low-ticket offer that leads to a "high ticket offer coaching program"
- Location / timezone: United Kingdom (UK time, GMT/BST)
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
- GoHighLevel ("go high level"), where he has already "designed an automation" to sell the offer.

## Every number in the post
- None about his business. The post names no offer, no price, no list size, no traffic numbers.
- Metadata: Hourly $7-$25, intermediate, part time; 6 invites; recorded bids avg $20.10 (basis unspecified); posted 2026-09-28.
- Missing numbers he obviously has (offer price, coaching price, treatment client list size, traffic) go under "Ask before quoting" in assessment.md. On the build: the offer is a clearly labelled sample offer and no price appears anywhere.

## Their requirements, verbatim, in their order
1. "I am working on a low ticket offer which I have designed an automation on go high level to aim to sell this."
2. "The idea is to eventually sell my high ticket offer coaching program, that is the next step"
3. "for now I need help with the right automation and customer journey to sell my low ticket offer."

3 parts in the post, 6 scenes in the film. Parts 1 and 3 share the journey scenes 1 to 3 (the visitor, the sale, delivery); part 2 is scenes 4 and 5 (nurture, then the coaching call); scene 6 shows the automations behind it, starting from the one he designed.

## The odd ask only they would recognize
He has already "designed an automation on go high level" and wants help making it "the right" one. On screen: scene 6's first workflow is "Your offer automation, as you designed it", reviewed and kept as the starting point, and the beat names it. Second detail: he does individual treatments today, so "Treatment clients" is one of the journey's entry sources.

## What their hiring history implies
Client record not pulled. Six invites and a $7-$25 hourly range suggest a solo owner early in building the funnel, who wants someone to make it work and explain the journey, not a strategy deck. The question "Is this something you can help me with?" reads as open and a little unsure: show the finished journey plainly.

## Their likely data
One low-ticket buyer moving through GoHighLevel. The offer is a sample ("The 7-Day Reset"), no price.

```json
{
  "contact": "Hannah Reid",
  "email": "hannah.reid@example.com",
  "phone": "+44 7700 900123",
  "source": "Instagram",
  "offer": "The 7-Day Reset (sample offer)",
  "order": "DN-1042",
  "order_bump": "Recipe Pack",
  "tags": ["reset-buyer", "recipe-pack"],
  "program_progress": "Day 7 of 7",
  "check_in_day_3": "4/5, more energy already",
  "engagement_score": 85,
  "pipeline_stage": "Ready for coaching",
  "coaching_call": "Thu 18:00 with Sandro"
}
```

## Sizing (setup / infrastructure / method jobs only)
Not a sizing job. The one design decision worth showing: the coaching invite goes out on engagement (finished all 7 days, replied to a check-in, clicked "tell me about coaching"), not at checkout; buyers who are not ready drop into a slower nurture instead of being pushed. This is on screen (scene 4, sample threshold of 70) and in a beat.

## Three things they would recognize on screen
1. Detox Nation in the top bar, and his path "low ticket offer, then the high ticket coaching program" as the scene 1 journey ending in "Coaching program".
2. "Your offer automation, as you designed it" as the first workflow in scene 6, and in a beat.
3. His individual treatments: "Treatment clients" as an entry source in scene 1; and he takes the coaching call himself ("call with Sandro", call brief for Sandro in scene 5).

## Beat 1 draft
"This is a working prototype of your low-ticket customer journey." (Sandro, this is the path from your low-ticket offer to your coaching program, for Detox Nation.)
