# Dossier - GoHighLevel Expert Needed — Dental/Orthodontic CRM, Automation & Patient Tracking

url: https://www.upwork.com/jobs/~022103189057814053377

## Who they are
- First name: unknown (no `client first name:` line, post is unsigned)
- Company: unknown (the post names no practice)
- Industry: "multi-location dental and orthodontic practice" providing "both general dentistry and orthodontics, including Invisalign and braces"
- Location / timezone: South Florida, US (America/New_York); offices in Pembroke Pines, Boynton Beach, Royal Palm Beach
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
In order of appearance: GoHighLevel (GHL), GHL snapshot (what they do NOT want), Google Ads, Meta Ads, Website, Phone Call, Google Ads offline conversion tracking / enhanced conversions for leads, Meta/Facebook (lead tracking), SMS/email, their dental practice-management system (PMS, not named), AI calling (future), Zapier, Make, n8n, Twilio. They ask which dental PMS we have integrated; they never say which one they run.

## Every number in the post
- "We have 3 locations": Pembroke Pines, Boynton Beach, Royal Palm Beach
- 10 numbered scope items (1. Multi-Location CRM Setup ... 10. AI / Future Automation)
- 11 pipeline stages listed: New Lead, Attempted Contact, Contacted, Appointment Scheduled, Confirmed, Showed, No Show, Rescheduled, Treatment Presented, Became Patient, Treatment Started (counted from the list)
- 4 named services: General Dental, Orthodontics, Invisalign, Braces ("Other major services where appropriate")
- 4 lead sources in the primary goal: Google Ads / Meta Ads / Website / Phone Call
- 4 conversion events for Google: Appointment scheduled, Appointment showed, Became patient, Treatment started
- 12 follow-up situations in part 6 (New leads, Missed calls, Caller did not schedule, Form lead did not schedule, Appointment reminders, Appointment confirmation, No-shows, Cancelled appointments, Unresponsive leads, Treatment follow-up, Recall/reactivation, Review requests; counted)
- 3 named recall types plus "other": Hygiene/recall, Unscheduled treatment, Orthodontic consultations
- 11 dashboard metrics in part 9 (counted)
- 7 AI use cases in part 10 (counted)
- 14 questions they want answered
- 5 potential milestones
- "A large percentage of our new patients call the office" (no figure given)
- Metadata: hourly listing, budget not provided, expert, part time, "prefer a fixed-price project with milestones"; bids avg $31.36, range $8-$85; 12 connects; 1 invite; new to Upwork, 0 contracts, 0 reviews, $0 spent
- Not given (their inputs, never stated as facts): monthly leads and calls per location, which PMS, current phone system, recall list size, number of staff users, who runs their ads

## Their requirements, verbatim, in their order
1. "Multi-Location CRM Setup ... Configure GoHighLevel appropriately for our three locations. We need to distinguish between: Pembroke Pines Boynton Beach Royal Palm Beach General Dental Orthodontics Invisalign Braces"
2. "Patient Pipeline ... Create appropriate pipelines/stages such as: New Lead → Attempted Contact → Contacted → Appointment Scheduled → Confirmed → Showed → No Show → Rescheduled → Treatment Presented → Became Patient → Treatment Started"
3. "Phone Call Tracking ... Calls that do NOT result in an appointment should automatically enter an appropriate follow-up process."
4. "Google Ads Tracking & Offline Conversions ... We want qualified conversion events sent back to Google when appropriate, such as: Appointment scheduled Appointment showed Became patient Treatment started"
5. "Meta/Facebook Lead Tracking ... We want the original source retained throughout the patient's journey."
6. "Automated Follow-Up ... The system should prevent patients from receiving inappropriate messages after their status changes."
7. "Recall & Patient Reactivation ... Hygiene/recall Unscheduled treatment Orthodontic consultations Other appropriate reactivation campaigns"
8. "Practice Management System Integration ... avoid unnecessary duplicate data entry and, where technically possible, allow important patient status changes to update our marketing/CRM workflows."
9. "Dashboard & Reporting ... simple reporting by location and lead source ... We should be able to compare our three locations."
10. "AI / Future Automation ... designed so AI calling can be added later without rebuilding the entire CRM."
Cross-cutting, not numbered: "HIPAA / Security ... understand the limitations of marketing CRM systems when handling PHI" and "Ownership ... We do not want our business dependent upon an agency-owned CRM account."

10 parts in the post, 5 bands on the chart (grouped adjacent, in order, matching their own milestones):
- Band 1 = parts 1 and 2 (their milestone 1)
- Band 2 = parts 3, 4 and 5 (their milestone 2, plus part 4's offline conversions from their milestone 4)
- Band 3 = parts 6 and 7 (their milestone 3)
- Band 4 = part 8 (their milestone 4)
- Band 5 = parts 9 and 10 (their milestone 5)
Ownership lands on step 1 ("Your Own GHL Account"); PHI lands in the band 2 and band 4 notes.

## The odd ask only they would recognize
"This is NOT simply a request to install a generic GHL snapshot" together with "We do not want our business dependent upon an agency-owned CRM account." On screen: step 1, "Your Own GHL Account, One Pipeline per Location, No Generic Snapshot". Named in beat 2.

## What their hiring history implies
First job on Upwork: 0 contracts, $0 spent, 1 invite sent. They wrote a long, exact brief with 14 questions and "Please do NOT send a generic proposal", and the snapshot and agency-account lines read like they have been sold a template before. They will screen on direct, honest answers to each question and on whether the builder understands attribution past the phone call. Portfolio questions (dental GHL count, a healthcare system to show, PMS integrations) will be answered "no" honestly, so the chart and the plan have to carry the pitch.

## Their likely data
One new-patient lead at the Pembroke Pines office, illustrative:

```json
{
  "contact": "Daniela Ruiz",
  "phone": "(954) 555-0183",
  "location": "Pembroke Pines",
  "service": "Invisalign",
  "first_source": "Google Ads",
  "campaign": "Invisalign - Pembroke Pines - Search",
  "gclid": "Cj0KCQjw9eG3BhCnARIsAKzvHn2tQx",
  "channel": "Phone call",
  "call_outcome": "Did not schedule - checking insurance first",
  "stage": "Attempted Contact",
  "received": "2026-09-22 10:14"
}
```

## Sizing (setup / infrastructure / method jobs only)
From their own numbers only:
- 12 follow-up situations x 3 locations: 36 workflow copies if each location is its own sub-account, 12 workflows if one account serves all 3 with a Location field. Every later change is made once instead of three times. This is the sharpest sizing point: on the chart (band 3 note) and in beat 6.
- 3 locations x 11 stages: one pipeline per location with the same 11 stages, so the dashboard compares Pembroke Pines, Boynton Beach and Royal Palm Beach by pipeline.
- 4 conversion events: 4 conversion actions in Google Ads shared by all 3 locations (the campaign already carries the location), not 12.
- 3 locations x 3 non-phone sources (Google Ads, Meta Ads, Website) = 9 source tracking numbers at minimum before any website number pool; pool size depends on their web traffic (their input).
- Google accepts an offline conversion only inside the conversion action's click window, 90 days at most. Became Patient and Treatment Started on ortho cases can land later than that; those count on their dashboard but not in Google. Which stage Google bids on depends on their monthly volume per stage (their input).

## Three things they would recognize on screen
1. Their three offices, Pembroke Pines, Boynton Beach, Royal Palm Beach: chart title and the band 5 note; their services General Dental, Orthodontics, Invisalign, Braces on step 2.
2. Their 11 stage names in the band 1 note, and their four conversion events on step 6: "Google Ads Gets Scheduled, Showed, Became Patient, Treatment Started".
3. Their "Caller did not schedule" follow-up and "prevent patients from receiving inappropriate messages after their status changes": step 7, gate 8 "Status Changed Before the Next Message?", band 3 note.

## Beat 1 draft
"This is ad source to actual patient for your three-location dental practice."
