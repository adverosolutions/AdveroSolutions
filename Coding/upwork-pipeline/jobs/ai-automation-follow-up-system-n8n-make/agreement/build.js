const fs = require("fs");
const { Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell, WidthType, AlignmentType, BorderStyle, ShadingType, LevelFormat, TabStopType } = require("docx");

const FONT = "Calibri";
const NAVY = "1F3A5F";
const GRAY = "555555";
const LIGHT = "EEF2F7";

const p = (text, opts = {}) => new Paragraph({ spacing: { after: 120, line: 276 }, ...opts, children: [new TextRun({ text, font: FONT, size: 22, ...(opts.run || {}) })] });
const runs = (parts, opts = {}) => new Paragraph({ spacing: { after: 120, line: 276 }, ...opts, children: parts.map(([t, r]) => new TextRun({ text: t, font: FONT, size: 22, ...(r || {}) })) });
const h1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 320, after: 120 }, children: [new TextRun({ text, font: FONT, size: 28, bold: true, color: NAVY })] });
const h2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 200, after: 80 }, children: [new TextRun({ text, font: FONT, size: 23, bold: true, color: NAVY })] });
const bullet = (text, ref = "bullets") => new Paragraph({ numbering: { reference: ref, level: 0 }, spacing: { after: 80, line: 276 }, children: [new TextRun({ text, font: FONT, size: 22 })] });
const bulletRuns = (parts) => new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 80, line: 276 }, children: parts.map(([t, r]) => new TextRun({ text: t, font: FONT, size: 22, ...(r || {}) })) });

const border = { style: BorderStyle.SINGLE, size: 4, color: "BFC7D1" };
const borders = { top: border, bottom: border, left: border, right: border };
const cell = (text, width, opts = {}) => new TableCell({
  width: { size: width, type: WidthType.DXA }, borders,
  shading: opts.head ? { type: ShadingType.CLEAR, fill: LIGHT, color: "auto" } : undefined,
  margins: { top: 80, bottom: 80, left: 120, right: 120 },
  children: (Array.isArray(text) ? text : [text]).map(t => new Paragraph({ spacing: { after: 40, line: 260 }, alignment: opts.align || AlignmentType.LEFT, children: [new TextRun({ text: t, font: FONT, size: 21, bold: !!opts.head || !!opts.bold })] })),
});
const table = (widths, rows) => new Table({
  width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths,
  rows: rows.map((r, i) => new TableRow({ tableHeader: i === 0, children: r.map((c, j) => cell(c, widths[j], { head: i === 0, align: (i > 0 && j === r.length - 1 && r.length === 2 && widths.length === 2 && rows[0][1].startsWith("Amount")) ? AlignmentType.RIGHT : AlignmentType.LEFT })) })),
});

const W = 9360; // 6.5in text width

const doc = new Document({
  styles: { default: { document: { run: { font: FONT, size: 22 } } } },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
    { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
  ] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
    children: [
      new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: "PROPOSAL AND STATEMENT OF WORK", font: FONT, size: 20, bold: true, color: GRAY, characterSpacing: 40 })] }),
      new Paragraph({ spacing: { after: 240 }, border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: NAVY, space: 8 } }, children: [new TextRun({ text: "Bid and Follow-Up Automation System", font: FONT, size: 40, bold: true, color: NAVY })] }),

      table([2600, 6760], [
        ["Item", "Detail"],
        ["Prepared for", "Jennifer Lawson"],
        ["Prepared by", "Lorenzo Villarreal, AdveroSolutions"],
        ["Proposal date", "September 12, 2026"],
        ["Delivery deadline", "Monday, September 14, 2026, 9:00 PM Central Time"],
        ["Fixed price", "$528.64 USD, processed through Upwork"],
        ["Platform", "n8n, with Twilio for text messaging"],
      ]),

      h1("1. Project Summary"),
      p("This proposal covers the design, build, testing, and handoff of one automated bid and follow-up system for Jennifer Lawson's business. Once a bid or estimate goes out, the system tracks it and follows up with the customer by email and text message on a set schedule, stops the moment the customer replies or books, and lets your team know. The goal we agreed on during our call is simple: no bid goes cold because nobody had time to chase it."),
      p("This is a full-service build. I handle the workflow, the message templates, the Twilio steps, the testing, and the handoff. You provide access to your existing tools, a short review of the message copy, and your own Twilio account details once the build is done."),

      h1("2. Goal"),
      p("Automate follow-up on every outstanding bid through two channels, email and text (via Twilio), so that:"),
      bullet("Every bid that goes out is logged and tracked in one place."),
      bullet("Customers receive timely, personal follow-ups without anyone on your team remembering to send them."),
      bullet("Follow-ups stop automatically when the customer responds, accepts, or declines."),
      bullet("Your team is notified the moment a customer replies, so a warm lead is never left waiting."),

      h1("3. Scope of Work"),
      h2("3.1 Bid intake and tracking"),
      bullet("A trigger that starts the sequence when a new bid is sent or logged from your website form."),
      bullet("A bid tracking record (Google Sheet or your existing CRM) holding customer name, phone, email, project, bid amount, date sent, current status, and last touch."),
      bullet("Status values: Sent, Following Up, Replied, Booked, Declined, No Response."),
      h2("3.2 Email follow-up"),
      bullet("A timed sequence of follow-up emails sent from your business email account, personalized with the customer's name, project, and bid details."),
      bullet("Cadence: day 1, day 3, day 7, and day 14 after the bid goes out. Sends are limited to business hours in Central Time."),
      h2("3.3 Text follow-up via Twilio"),
      bullet("A matching sequence of short text messages sent through Twilio, timed to alternate with the emails so the customer is never hit on both channels in the same day. The Twilio steps are built and tested in full; you plug in your own Twilio account (number and API keys) once the build is delivered, and I confirm the first live text during the support window."),
      bullet("Opt-out handling: a reply of STOP ends all messaging to that number immediately, as Twilio and US carrier rules require."),
      h2("3.4 Reply handling and stop rules"),
      bullet("Inbound text replies are captured through a Twilio webhook. Inbound email replies are detected on the sending inbox."),
      bullet("Any reply marks the bid as Replied and stops the remaining touches for that customer."),
      bullet("Marking a bid Booked or Declined in the tracker also stops the sequence."),
      h2("3.5 Notifications"),
      bullet("When a customer replies, your team gets an alert with the customer's name, the bid, and the message, delivered by text and email."),
      bullet("A short daily summary of bids still in follow-up and any replies received in the last 24 hours."),
      h2("3.6 Message templates"),
      bullet("Up to four email templates and four text templates, written by me in your voice, reviewed and approved by you before go-live."),
      bullet("All templates stay editable by your team after handoff without touching the workflow."),
      h2("3.7 Testing and handoff"),
      bullet("End-to-end testing with at least three test bids using your real accounts, covering a full sequence, a reply mid-sequence, and a STOP."),
      bullet("A recorded walkthrough video showing how the system works, how to change a template, and how to pause or restart a customer's sequence."),
      bullet("Seven days of post-delivery support for bug fixes and small adjustments to timing or copy."),

      h1("4. Deliverables"),
      table([3200, 6160], [
        ["Deliverable", "Description"],
        ["Live workflow", "The bid and follow-up automation, built and running in your n8n account."],
        ["Bid tracker", "Google Sheet or CRM view with every bid, its status, and its last touch."],
        ["Message templates", "Up to four email and four text templates, approved by you."],
        ["Twilio steps", "Sending, inbound webhook, and STOP handling built and tested. You connect your own Twilio account after delivery using the one-page guide included."],
        ["Walkthrough video", "Recorded handoff covering daily use and template changes."],
        ["Support window", "Seven days of fixes and adjustments after delivery."],
      ]),

      h1("5. Not Included"),
      bullet("Monthly subscription or usage fees for n8n, Make.com, Twilio, email sending, or any other third-party service. These are billed by those providers directly to you."),
      bullet("Twilio A2P 10DLC registration fees or carrier fees."),
      bullet("Additional follow-up sequences beyond the one bid and follow-up system described above (for example, a separate sequence for new leads before a bid goes out). These can be quoted separately."),
      bullet("Migrating data into a new CRM, or building a CRM."),
      bullet("Advertising, lead generation, or website changes."),

      h1("6. What I Need From You"),
      p("The 24 to 48 hour timeline depends on having these in hand at kickoff:"),
      bullet("A sample of three recent bids so the tracker and templates match how you actually quote.", "numbers"),
      bullet("A Twilio account in your name, with a number, ready to connect after delivery. If you do not have one yet, the included guide walks you through creating it in about ten minutes.", "numbers"),
      bullet("The business email account the follow-ups should send from.", "numbers"),
      bullet("Access to your n8n account, or your approval for me to set one up in your name.", "numbers"),
      bullet("Access to the website form (or its notification email) so new bids can start the sequence.", "numbers"),
      bullet("Any follow-up messages you send today, even rough ones, so the templates sound like you.", "numbers"),
      bullet("Template approval within a few hours of receiving them, since the build waits on the copy.", "numbers"),
      bullet("A team member's mobile number or email for reply notifications.", "numbers"),

      h1("7. Timeline"),
      p("Work begins as soon as the Upwork milestone is funded and access is provided. Delivery is 24 to 48 hours from that point, and no later than Monday, September 14, 2026, at 9:00 PM Central Time."),
      table([2400, 6960], [
        ["Stage", "What happens"],
        ["Kickoff (hour 0)", "Milestone funded, access received, cadence and channels confirmed."],
        ["Build (hours 0 to 24)", "Tracker, email sequence, Twilio text sequence, reply handling, and notifications built. Templates sent to you for approval."],
        ["Test (hours 24 to 40)", "Three test bids run end to end, email from your account and texts through a test Twilio number. Fixes applied."],
        ["Delivery (by hour 48)", "System live, walkthrough video and Twilio connection guide delivered, milestone submitted for release."],
        ["Support (days 1 to 7)", "You connect your Twilio account, I confirm the first live text. Bug fixes and small timing or copy adjustments included."],
      ]),
      runs([["A note on text messaging. ", { bold: true }], ["The complete system, including every text step, is built and tested by the deadline. Texts start sending to real customers as soon as you connect your Twilio account after delivery. US carriers also require business texting numbers to be registered with Twilio (A2P 10DLC), which Twilio usually approves in one to seven business days; the included guide covers submitting it. Email follow-ups are not affected by any of this."]], { spacing: { before: 160, after: 120 } }),

      h1("8. Investment"),
      table([6960, 2400], [
        ["Item", "Amount (USD)"],
        ["Bid and Follow-Up Automation System, full-service build as described in Sections 3 and 4", "$528.64"],
        ["Total, fixed price", "$528.64"],
      ]),
      h2("Payment terms"),
      bullet("All payments are processed through Upwork. No payment is requested or accepted outside the Upwork platform."),
      bullet("The full amount is funded into Upwork escrow as a single milestone before work begins. Funding the milestone is what starts the 24 to 48 hour clock."),
      bullet("The milestone is submitted for release on delivery, once the acceptance criteria in Section 9 are met. Upwork's standard review period applies."),
      bullet("Third-party costs (Twilio usage, subscriptions, registration fees) are paid by you directly to those providers and are not part of this price."),
      bullet("Upwork's Terms of Service govern the contract, payment protection, and dispute resolution for both parties."),

      h1("9. Acceptance Criteria"),
      p("The build is considered delivered when all of the following are demonstrated with a test bid in your accounts:"),
      bullet("A new bid entered at the source appears in the tracker with status Sent.", "numbers"),
      bullet("The first email goes out on schedule from your account and the first text goes out through the test Twilio number, both personalized correctly.", "numbers"),
      bullet("A text reply from the customer stops the sequence, updates the status to Replied, and triggers a notification to your team.", "numbers"),
      bullet("An email reply does the same.", "numbers"),
      bullet("A STOP reply ends texting to that number.", "numbers"),
      bullet("The walkthrough video and the Twilio connection guide have been delivered.", "numbers"),

      h1("10. Terms"),
      bulletRuns([["Ownership. ", { bold: true }], ["On release of the milestone, the workflow, templates, and configuration belong to you and live in accounts you own. Nothing depends on my accounts."]]),
      bulletRuns([["Changes. ", { bold: true }], ["Requests beyond the scope in Section 3 are welcome and will be quoted separately as a new Upwork milestone before any additional work starts."]]),
      bulletRuns([["Support. ", { bold: true }], ["Seven days of included support begins on delivery. Ongoing maintenance after that can be arranged as a separate agreement."]]),
      bulletRuns([["Confidentiality. ", { bold: true }], ["Customer data, bid amounts, and account access are used only to build and test this system and are never shared."]]),
      bulletRuns([["Communication. ", { bold: true }], ["Project communication and file sharing stay on Upwork messages, in line with Upwork's policies."]]),
      bulletRuns([["Validity. ", { bold: true }], ["This proposal and the Monday, September 14, 2026 delivery deadline are valid if the milestone is funded by Saturday, September 12, 2026. If funding happens later, delivery remains 24 to 48 hours from funding."]]),

      h1("11. Acceptance"),
      p("Accepting the Upwork offer and funding the milestone constitutes acceptance of this proposal and statement of work. No signature is required."),
      p(""),
      table([4680, 4680], [
        ["Prepared by", "Accepted by"],
        [["Lorenzo Villarreal", "AdveroSolutions", "September 12, 2026"], ["Jennifer Lawson", "Date: ____________________"]],
      ]),
    ],
  }],
});

Packer.toBuffer(doc).then(buf => { fs.writeFileSync("Bid-and-Follow-Up-System-Proposal.docx", buf); console.log("written"); });
