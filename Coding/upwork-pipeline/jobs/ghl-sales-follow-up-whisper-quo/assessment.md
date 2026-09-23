# Private assessment - Go High Level Workflow Setup (whisper + Quo hosted messaging)

**Time.** 3 to 5 hours of real work if the Quo number is already hosted into GHL and the
Sales Request form already collects lead source, square footage and desired service. Build
the workflow, wire the pipeline and tags, set the user's phone for the whisper call, test
the connect-then-whisper path end to end on two live phones, then the reply catcher. Add a
week of calendar time if the number is not hosted yet: that is a carrier step, not a build
step. Realistic: one working session for the build, a second short one after the number
clears.

**Likelihood.** The workflow itself is routine for me and low risk. Two real dependencies
sit outside the workflow:
- **Quo hosted messaging.** Quo is OpenPhone rebranded. Texting from their business number
  inside GHL means hosting that number's SMS with LeadConnector, which the client submits
  from Settings, Phone Numbers, and the carrier takes roughly 1 to 5 business days. I
  cannot do that step for them and they cannot skip it. Until it clears, texts would go
  from a new GHL number, which is exactly the "replies did not come to our number" failure
  they are trying to avoid. Calls still stay on Quo; only the SMS leg is hosted.
- **The whisper call.** GHL's automated Call action needs their GHL phone system live and a
  phone number on the user profile that should be rung. Whisper text is read to the user
  only, then the contact is bridged. If the rep does not answer inside the ring timeout the
  call is treated as not connected and the sequence takes over, which is why the build has
  the If/Else instead of assuming a connect.
- **Unverified for me:** I have not personally hosted a Quo number into a client's GHL. I
  have built GHL workflows and hosted-number setups on other carriers. I will say that
  plainly and offer to do the hosting request on a screenshare with them rather than claim
  it is a one-click thing.
- **Client risk.** Their last SMS and email automation contract ended with them leaving 1
  star. That is the important signal in this post: expect someone who was promised "it just
  works" and got a half-finished sequence. Mitigation is the Loom of a real built workflow
  before a word of scoping, plus the two prerequisites named up front instead of discovered
  in week two. 45 contracts, $16k spent, 4.87 over 10 reviews, 2,928 hours, so they hire
  constantly and they are not a tyre-kicker.
- **1 offer is already out** and every recorded bid is exactly $100, so the post is being
  treated as a fixed price shelf item. Speed and the working demo are the only edge.
- Prefers native English. No location asserted in the copy.

**Standard pricing.** A whisper-connect call plus a five-touch email/SMS/manual-call
sequence with pipeline tracking and a reply catcher is a $300 to $600 fixed build at market,
$450 being the honest middle. The post is $100. Bid it as the entry point, not the ceiling:
the follow-on work here is obvious (the five SEO contracts, the Zapier mess, the sequence
that burned them) and this is the cheapest way to be the person who actually shipped one.
Recurring software is on them: GHL plan they already have, hosted messaging is free to host
but SMS is billed per segment through LeadConnector, and Quo stays on its own plan for
voice.

**Ask before quoting.**
1. Is the Quo number already hosted into GHL for SMS, or does that request still need to be
   submitted? Everything on the text side hangs on this answer.
2. Which form is the sales request, the exact name, and does it already capture lead source,
   square footage and desired service as contact fields?
3. Who should the whisper call ring: one owner, or the assigned user round robin, and is
   their number already on their GHL user profile?
4. What hours should the call step run? Ringing the owner at 11pm on a form fill is the
   fastest way to get this turned off.
5. Do they want the email touches sending from GHL, or from their existing sender through a
   connected mailbox?
