# Their 14 questions (reference only; skill rule 9: not answered point by point in the proposal. Use for a text box or the call; fill every [LORENZO])

1. **How many dental practices have you personally configured in GoHighLevel?**
None so far. The chart in my Loom is drawn from your post: your three offices, your 11 stages and the four events you want sent to Google Ads.

2. **Can you show us a dental GHL system or similar healthcare system you personally built?**
No, I have no dental or healthcare system to show. The nearest is a routing and follow-up system I built for a commercial roofing contractor: every estimate request is tracked and followed up, and $750M+ in annual bid volume runs through it. [LORENZO: confirm you can show a screen of it before offering to.]

3. **How would you structure GHL for 3 locations offering both general dentistry and orthodontics?**
One sub-account in a HighLevel account you own, with a pipeline each for Pembroke Pines, Boynton Beach and Royal Palm Beach carrying the same stages, a calendar and tracking numbers per location, and a Service field for General Dental, Orthodontics, Invisalign and Braces. One account keeps a patient as one contact across all three offices, lets the dashboard compare the locations, and turns your 12 follow-up situations into 12 workflows instead of 36. If each front desk must see only its own patients, we weigh three sub-accounts instead in milestone 1.

4. **Explain how you would track a patient from a Google Ads click or phone call all the way through becoming an actual patient.**
The Google click ID and UTM source are saved from your website forms, and a GHL number pool that swaps the phone number by visitor source ties website calls to their source (whether it carries the click ID too is checked in milestone 2), and calls placed straight from a Google ad carry no click ID, so they go through Google forwarding numbers and Google's call conversion import; the first source goes into fields nothing overwrites. Every call or form opens an opportunity in that location's pipeline, and the front desk or your PMS moves it from Appointment Scheduled through Showed and Became Patient to Treatment Started. Each move sends the matching conversion with the click ID to Google Ads and counts on the dashboard by location, source and campaign.

5. **Have you personally implemented Google Ads offline conversions or enhanced conversions for leads from GoHighLevel? Please describe the implementation.**
No, I haven't implemented Google Ads offline conversions or enhanced conversions for leads. I would create four conversion actions in your Google Ads account (Scheduled, Showed, Became Patient, Treatment Started), have a GHL workflow on each stage change send the click ID, conversion name and time through a scheduled Google Ads import or the Google Ads API from n8n, and check test conversions before any bidding change. Google only accepts a conversion inside the action's click window, 90 days at most, and bidding needs steady volume, so the deeper stages may start as secondary goals until your monthly numbers support them.

6. **How would you handle someone who calls the office but does NOT schedule an appointment?**
The front desk marks the call outcome, and "did not schedule" (or a missed call) starts a text-back from that location's number, then a short follow-up sequence. Every message checks the stage first, so the sequence stops the moment they reach Appointment Scheduled, and anyone who never replies moves to your reactivation list.

7. **Which dental practice-management systems have you integrated with GHL?**
None. Tell me which PMS each office runs and I'll confirm its route before milestone 4: its own API, an approved sync partner, a scheduled export, or, where none exists, the front desk moving the stage in GHL.

8. **How would you prevent duplicate patient/contact records?**
GHL's duplicate setting matches on phone and email, so a caller who later fills in a form stays one contact, and one account for all three offices keeps a patient who visits two locations as one record. Parents and children often share a phone number, so the contact is the person who called and each family member gets their own opportunity. Once a patient is in your PMS, their PMS ID goes on the contact and any sync matches on it first.

9. **Have you built recall/reactivation campaigns for dental practices?**
No. I'd build one campaign per list from your PMS (hygiene due or overdue, unscheduled treatment, orthodontic consults who didn't start), each stopping as soon as the patient books.

10. **Have you implemented AI inbound or outbound phone agents with GHL?**
No. I use Claude and the Anthropic API daily, and this build keeps stages, call outcomes and calendars in named fields so an AI agent, HighLevel's own or another provider's, can read and write them later without rebuilding the CRM.

11. **How would you handle HIPAA/PHI considerations?**
GHL holds what marketing needs (name, phone, email, location, service, source and stage); clinical notes, diagnoses, x-rays and insurance details stay in your PMS, and reminder texts name the office and time, not the treatment. Before patient data goes in, we check whether HighLevel's HIPAA option and a signed BAA are active on your account, and your compliance advisor signs off on what goes back to Google Ads; my default is click ID, stage and time, with no names or treatment details.

12. **Will the entire system be built inside accounts that we own and control?**
Yes. The HighLevel account, phone numbers, Google Ads and Meta connections, any n8n or Make bridge and the documentation all sit in accounts you own, and I work in them as a user you can remove at any time. If you are on an agency's sub-account today, moving to your own HighLevel account is the first step of milestone 1.

13. **What would you charge as a fixed project price for this implementation?**
$4,800 fixed [LORENZO: confirm], split over your five milestones: $700, $1,100, $1,300, $1,000 and $700. Software stays in your name and on your bill: your HighLevel plan, phone and SMS usage, and a PMS sync fee if your PMS needs one.

14. **Approximately how long would implementation and testing take?**
About 6 weeks [LORENZO: confirm], with milestone 1 done in week 1. SMS carrier registration (A2P 10DLC), which I'd file on day one, and your PMS's integration route are the two things that can stretch it.
