# Private assessment — not for the proposal

**What they actually asked for:** research first, then a step by step PDF with images. Not the build. The n8n canvas is the prop that proves the guide describes something real.

## Time
- Research phase: 5-8 hrs. Reading Docketwise, Otter, RingCentral and Graph docs, checking what each plan tier actually exposes, standing up trial/dev accounts where possible.
- PDF with screenshots and illustrations: 6-9 hrs. Screenshots are the slow part and they have to come from real consoles, not mockups.
- Realistic total 12-17 hrs over 1.5-2 weeks, most of the calendar time waiting on their account access.
- Building the integration is a separate phase entirely: 25-40 hrs.

## Likelihood — what could actually break
- **Docketwise API access is unverified.** I have not confirmed they publish a documented public API, or that this firm's plan includes it. If write access to matter notes is not available, the whole thing changes shape and the guide has to document a workaround instead. This is exactly the question the research phase exists to answer, so it is not a reason to walk, but it must be said out loud before the contract, not discovered in week two.
- **Otter's webhook/API is plan gated and unverified.** Programmatic access to a finished transcript is a Business/Enterprise level feature on most tools of this type. If their plan does not have it, the fallback is Otter's email or cloud export, which is slower and messier but documentable.
- **RingCentral is the most likely of the three to be straightforward**, but call recording scopes usually need an admin-approved developer app, and that lives in their account, not mine.
- **Zapier and Power Automate are real alternatives to n8n here** and the post already names them. Whichever path the research says is actually possible is the one the PDF documents. Do not promise n8n specifically.
- **Attorney-client confidentiality is the live risk.** Immigration client transcripts going to any third-party model needs the firm's explicit sign-off, a no-training commitment, and a documented retention position. Raise it before they raise it, and put a section on it in the PDF.
- Two matters for one client, or a shared household phone number, both produce ambiguous matches. The build must escalate to a human, never guess. Wrong note on the wrong file is worse than no note.

## Standard pricing
- Research + documented step by step PDF, expert tier: **$800-1,500** is the defensible market range for this scope.
- $400 fixed is below that, and the avg bid of ~$392 says the pool is anchoring to the posted number rather than the work. It is still worth taking as a door opener because the build is the real contract.
- Building the integration afterwards: **$3,000-6,000** fixed, or hourly at his rate.
- Recurring costs to name in the PDF: n8n cloud or self-host, Otter Business seats, an LLM API line of roughly $20-60/mo at this volume.

## Ask before quoting
1. Which Otter plan are they on, and does it show webhooks or an API in the admin panel?
2. Has anyone at the firm asked Docketwise support for API credentials yet, and what did they say?
3. Who has RingCentral admin, and can they approve a developer app with call recording scope?
4. Is the firm comfortable with transcripts being processed by a third-party AI model, and do they need a signed DPA or a no-training guarantee first?
5. Should the PDF document all three routes (API, Zapier, Power Automate) or only the one the research says works best?
6. Do they want the build itself quoted as a phase two now, or after they read the guide?
