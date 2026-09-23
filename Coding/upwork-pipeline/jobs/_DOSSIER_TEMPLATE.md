# Dossier - <job title as posted>

Written by the job subagent from `jd.txt` BEFORE any spec (on a rebuild,
without opening the folder's older files; in a revise round, open it and apply
only the reviewer's fixes that name it). Every later file (spec.json,
beats.md, the reviewer's check) is built from this page, so it holds only what
the post, the metadata paragraph, `client.json` (when client intel ran) and
(when named) the client's own website say.
Never guess. When a field is unknown, write `unknown` and move on. An `unknown`
here is never copied into spec.json: the matching `client` key is omitted.

url: <upwork link from jd.txt>

## Who they are
- First name: <the `client first name:` line in the metadata paragraph when
  present (the main session's, or client intel's from freelancers' reviews),
  else as signed in the post, else unknown. The greeting and beat 1
  use it; when unknown they fall back as before ("Hey [firm] team" or "Hey
  there"; "this is <their outcome> for your <business type>")>
- Company: <as written in the post, or plainly inferable from it (their domain,
  their product name). Never invent or guess a company name; else unknown>
- Industry: <their business, in their words ("webinar host with an old list",
  "commercial roofing contractor"), not a category like "SMB">
- Location / timezone: <from the metadata paragraph>
- Website read: <url fetched read-only, or "none named">. If fetched: services,
  terminology they use, anything that should appear on screen.

## Client (from `client.json`; write "no client intel" when the file is missing)
Private. Never state a review fact to the client, on the build, in a beat or in
the proposal ("freelancers say you pay on time" never appears anywhere they
see). It only steers tone and emphasis.
- First name: <`derived.jd_first_name`, or "none confirmed">
- Grade: <`derived.grade` and `derived.reasons`, verbatim>
- What freelancers praise: <the `praise` themes with a count of 2 or more, in
  plain words ("clear requirements", "communication"), plus one short
  `fl_quotes` line if it sharpens the picture>
- How the client writes: <two or three words on tone from `client_voice`
  ("short and blunt", "warm, exclamation marks", "formal"), with one quote.
  This is the tone hint for the beats: match how they talk>

## Tools they named
<every app, platform or service in the post, verbatim, in the order they appear.
If none: the one tool you will commit to and why (from their history or post);
never "any CRM" or "placeholder">

## Every number in the post
<list each one with its context, verbatim: "10-20 domains", "old list", "$20
fixed", "5 nights a week", "3,200 sq ft". Include numbers from the metadata that
matter for the build (budget, hours). Missing numbers they obviously have (list
size, webinar date, lead volume) go under "Ask before quoting" in assessment.md
and as clearly labelled inputs on the build ("Your List Size"). A number about
their business that is not listed here, or worked out from these in Sizing,
is never stated as a fact anywhere.>

## Their requirements, verbatim, in their order
1. "<quote>"
2. "<quote>"
...
These become the sections of the build, one section per requirement, same order.
State the count: "N parts in your post, N sections on the canvas." Past 5
requirements, group adjacent ones into one section and write the grouping here
("parts 5 and 6 share section 5: ..."); the section note names it too. Fewer
than 4 sections is fine when the post asks for fewer things; never pad.

## The odd ask only they would recognize
<the one specific, unusual detail in the post ("I want a login to your software
and I add the list and press send", "without unnecessary complexity", a required
first word). It must be visible on screen and named in a beat.>

## What their hiring history implies
<from the metadata paragraph: spend, contract count, what they hired before,
reviews. What that says about how they judge work (a design buyer trying cold
email for the first time; a high-volume hirer of small fixed jobs who wants
something working, not a strategy deck)>

## Their likely data
<what one real record of theirs looks like: field names, a realistic name,
company, amount, date, status, in their industry and their units. This becomes
input_sample / output_sample and the sample rows in prompts. Never reuse
another client's names, companies or numbers.>

```json
{ "example": "one real-looking record of THEIR business" }
```

## Sizing (setup / infrastructure / method jobs only)
<their numbers run through the method: e.g. list size x weeks to the webinar ->
sends per day -> mailboxes -> domains -> pre-warmed or not. Show the arithmetic.
Use only numbers from "Every number in the post"; where one is missing, carry
it as their input ("your list size") and do not guess a value.
The sharpest insight here goes ON the chart and into a beat, not only into the
private assessment.>

## Three things they would recognize on screen
1. <their number / their tool / their odd ask, and where it appears (title,
   overview sticky, node label, sample, chart step)>
2. <...>
3. <...>

## Beat 1 draft
"<FirstName>, this is <their outcome in their words> for <company or their
business>" (first name unknown: "this is <their outcome> for your <business
type>")
