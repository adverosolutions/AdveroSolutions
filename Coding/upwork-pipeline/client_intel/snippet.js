/* Upwork client intel: page script + pure parser (v1, 2026-09-22).
 *
 * How the main session runs it (install once, then a short loader per job):
 *   1. INSTALL, once per version of this file, on any upwork.com page:
 *      `python3 client_intel.py --install-js` prints two small scripts. The
 *      first adds a file input (aria-label "advero client intel loader"); the
 *      Chrome tool's file_upload puts this file in it; the second reads it,
 *      checks its sha256 against the version baked in, stores
 *      {"v": <first 12 hex of sha256>, "src": <this file>} as JSON in
 *      localStorage["__advero_ci"] (upwork.com origin) and removes the input.
 *   2. RUN, per job page, once it has loaded: `python3 client_intel.py
 *      --loader` prints one line with the version baked in. It evaluates the
 *      stored text with __ADVERO_CI_NO_AUTORUN set (so the last line below
 *      does nothing), then awaits __clientIntel.runInPage() and returns the
 *      OBJECT. Wrong or missing install: {error: "stale_install", have, want}
 *      or {error: "not_installed"}; reinstall and run the loader again.
 *   3. The main session writes the returned object to <job>/client_raw.json
 *      (heredoc) and runs `python3 client_intel.py <job_dir> <job>/client_raw.json`.
 * Pasting this whole file into the javascript tool also works (the last line
 * then runs it); it is just slow.
 *
 * The result is compact because the tool truncates any string over about
 * 1,000 chars and any array over about 100 items: every string under 800
 * chars, every array under 40 items, the whole JSON under 5,000 chars.
 *
 * In the page it: waits up to 25 s for "About the client", clicks visible
 * "View more" buttons inside the client's history (up to 15 times, 1.5 s
 * apart), then parses document.body.innerText. A candidate must sit after
 * the history heading and before the first end marker the parser uses (Other
 * open jobs, footer, Similar jobs, Explore similar jobs), inside the history
 * section when it has one, and must not navigate (never an element with a
 * real href). It stops when a click adds no history record. It never clicks
 * anything else (a Cloudflare challenge is reported as an error, never
 * touched).
 *
 * Node tests load the parser from this same file (see test_client_intel.py):
 * the browser part only runs when `document` exists, and the parser is
 * exported through `module` when it exists.
 */
var __clientIntel = (function () {
  "use strict";

  var LIMITS = { str: 780, arr: 39, json: 4900 };

  var STOPWORDS = (
    "I Im Ive Id A An The This That These Those There Their They Them Then Than He His Him She Her Hers " +
    "We Our Us You Your Yours It Its Me My Mine Who What When Where Why How Which Very Really Truly " +
    "Great Good Nice Excellent Amazing Awesome Fantastic Wonderful Perfect Best Better Brilliant Superb Outstanding " +
    "Thank Thanks Thankyou Cheers Regards Sincerely Kind Best Hi Hello Hey Dear Sir Madam Mr Mrs Ms Miss Dr " +
    "Working Work Worked Was Were Is Are Be Been Being Has Have Had Having Will Would Could Should Can May Might " +
    "Everything Everyone Anyone Someone Nothing All Always Also And But So Or Nor Yet Such Both Each Every " +
    "Overall Highly Definitely Absolutely Certainly Again Just Only Easy Quick Fast Clear Communication " +
    "Client Buyer Employer Customer Team Company Project Job Task Contract Experience Pleasure Collaboration " +
    "Upwork Loom Zoom Slack Google Sheets Zapier Make Notion Airtable Shopify Wordpress God Jesus Lord " +
    "Monday Tuesday Wednesday Thursday Friday Saturday Sunday " +
    "January February March April May June July August September October November December " +
    "Jan Feb Mar Apr Jun Jul Aug Sep Sept Oct Nov Dec " +
    "Looking Hope Hoping Glad Happy Enjoyed Loved Appreciate Appreciated Recommend Recommended Highly " +
    "Professional Responsive Patient Friendly Helpful Fair Respectful Understanding Supportive Organized " +
    "One Two Three First Second Last Next Once Now Today Here Well Yes No Not Ok Okay Sure Lots Much Many More Most " +
    // forms of address and sign-offs that are not names
    "Bro Brother Bros Sis Sister Guys Guy Boss Buddy Mate Man Friend Friends Folks Fam Chief Champ Sir Madam Maam " +
    "Wish Wishes Wishing Cheers Hope Hopefully Blessings Bless Luck Success Regards Best Warm Warmly Take Care " +
    "Inc Ltd Llc Llp Co Corp Corporation Gmbh Group Agency Studio Studios Labs Media Solutions Holdings Enterprises " +
    // review nouns that start sentences
    "Payment Payments Feedback Instructions Requirements Deadline Deadlines Budget Delivery Response Responses " +
    "Support Quality Timeline Scope Details Brief Projects Tasks Communications Collaboration Partnership " +
    // automation / SaaS tools and brands (tool names also come from job titles, see extractNames)
    "Webflow Claude Chatgpt Openai Gpt Anthropic Gemini Hubspot Salesforce Gohighlevel Highlevel Ghl Clickup Asana " +
    "Trello Canva Figma Framer Wix Squarespace Bubble Lovable Bolt Clay Apollo Instantly Smartlead Lemlist " +
    "Calendly Stripe Quickbooks Xero Twilio Openphone Quo Retell Vapi Voiceflow Manychat Meta Facebook Instagram " +
    "Linkedin Tiktok Youtube Amazon Etsy Ebay Klaviyo Mailchimp Gmail Outlook Microsoft Apple Github Vercel " +
    "Supabase Firebase Pipedrive Zoho Keap Kajabi Teachable Skool Discord Telegram Whatsapp Python Javascript " +
    "Excel Docs Drive Wordpress Elementor Hostinger Godaddy Typeform Jotform Docusign Pandadoc Apify " +
    // US states (multi-word ones as their words)
    "Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida Georgia Hawaii Idaho " +
    "Illinois Indiana Iowa Kansas Kentucky Louisiana Maine Maryland Massachusetts Michigan Minnesota Mississippi " +
    "Missouri Montana Nebraska Nevada New Hampshire Jersey Mexico York North South Carolina Dakota Ohio Oklahoma " +
    "Oregon Pennsylvania Rhode Island Tennessee Texas Utah Vermont Virginia Washington West Wisconsin Wyoming " +
    "America Usa Canada"
  ).split(/\s+/).reduce(function (acc, w) { if (w) { acc[w.toLowerCase()] = true; } return acc; }, {});

  var RED_FLAGS = [
    ["did not agree", /did\s*n[o']?t agree/i],
    ["ended early", /ended early|end(?:ed)? the contract early|closed (?:the )?contract early/i],
    ["scope", /\bscope\b/i],
    ["unclear", /\bunclear\b/i],
    ["unresponsive", /unresponsive|not (?:very )?responsive|stopped responding|never responded|ghosted/i],
    ["late payment", /late payment|paid late|pay(?:ment)? (?:was )?(?:delayed|late)|never paid|not paid/i],
    ["dispute", /\bdisput/i],
    ["refund", /\brefund/i],
    ["micromanag", /micro-?manag/i],
    ["changed requirements", /chang(?:ed|ing|es) (?:the )?(?:requirements|scope|instructions)/i],
    ["low budget", /low budget|underpa(?:id|y)|budget (?:was|is) (?:too )?low/i],
    ["unprofessional", /unprofessional|\brude\b|disrespect/i]
  ];

  // Praise patterns carry word boundaries ("unclear instructions" is not
  // "clear instructions", "unresponsive" is not "responsive"). A praise match
  // is ignored when a negation or deficit sits a few words before it in the
  // same clause ("Lack of communication", "Not very responsive") or right after
  // it ("Communication could be much better"); see praiseHit.
  var PRAISE = [
    ["clear_requirements", /\b(?:clear (?:requirements|instructions|expectations|direction|brief|guidance|goals)|crystal clear|clear (?:with|on|about) (?:his|her|their|the) (?:requirements|expectations|needs|instructions)|(?:requirements|instructions|expectations) (?:were|was) (?:very |super )?clear|well[- ]defined|detailed instructions)\b/i],
    ["communication", /\bcommunicat/i],
    ["responsive", /\b(?:responsive(?:ness)?|quick to respond|quick (?:response|reply|replies|responses)|timely|respond(?:s|ed)? quickly|fast (?:response|reply)|prompt (?:response|reply|feedback))\b/i],
    ["fast_payment", /\b(?:(?:fast|quick|prompt|on[- ]time|instant|immediate) (?:pay|paid|payment)|paid (?:fast|quickly|promptly|on time|immediately)|pays? (?:fast|quickly|promptly|on time))\b/i],
    ["easy_to_work_with", /\b(?:easy to work with|pleasure (?:to work|working)|great (?:client|buyer|employer)|smooth(?:ly)?)\b/i],
    ["would_rehire", /\b(?:work (?:with (?:\w+ ){0,3})?(?:for )?again|future projects|work together again|continue (?:our|working))\b/i]
  ];

  // a negation or deficit word in the last few words before a praise match
  var PRAISE_NEG_BEFORE = /\b(?:not|no|never|lack|lacks|lacked|lacking|poor|poorly|bad|without|little|hardly|barely|slow|inconsistent|limited|minimal|zero|hard to|difficult)\b|n['’]t\b/i;
  // a deficit right after it, in the same clause
  var PRAISE_NEG_AFTER = /^\s*(?:(?:could|should) (?:be|have been|use|improve)|needs? (?:to be |some )?(?:improv|work)|(?:was|is|were|are)(?:n['’]t| not| lacking| poor| bad| slow| an issue| a problem| difficult| hard| hit or miss)|lacking|lacked|(?:was|is) (?:a bit|sometimes|often) (?:slow|lacking|poor|difficult))/i;
  // a red flag directly negated: "no scope creep", "never had a dispute", "not unclear"
  var FLAG_NEG_BEFORE = /(?:\b(?:no|not|never|zero|without|nor)|n['’]t)\s+(?:(?:any|a|an|real|major|big|single|much|further|more|serious|other|had|have|has|got|was|were|once|ever)\s+){0,2}$/i;

  function clauseBefore(text, idx) {
    var before = text.slice(0, idx);
    var cut = Math.max(before.search(/[^.!?;:,(]*$/), 0);
    var m = /^.*\b(?:but|however|although|though|yet)\b/i.exec(before.slice(cut));
    return m ? before.slice(cut + m[0].length) : before.slice(cut);
  }

  function clauseAfter(text, idx) {
    var after = text.slice(idx);
    var stop = after.search(/[.!?;:,)]|\b(?:but|however|although|though)\b/i);
    return stop === -1 ? after : after.slice(0, stop);
  }

  function globalRe(re) { return new RegExp(re.source, re.flags.indexOf("g") === -1 ? re.flags + "g" : re.flags); }

  function praiseHit(text, re) {
    var g = globalRe(re);
    var m;
    while ((m = g.exec(text))) {
      var words = clauseBefore(text, m.index).trim().split(/\s+/).slice(-3).join(" ");
      var e = m.index + m[0].length;
      while (e < text.length && /[\p{L}\p{M}]/u.test(text[e])) { e += 1; }  // "communicat|ion"
      var after = clauseAfter(text, e);
      if (!PRAISE_NEG_BEFORE.test(words) && !PRAISE_NEG_AFTER.test(after)) { return true; }
      if (m[0].length === 0) { g.lastIndex += 1; }
    }
    return false;
  }

  // the first red-flag match that is not directly negated, or null
  function flagMatch(text, re) {
    var g = globalRe(re);
    var m;
    while ((m = g.exec(text))) {
      if (!FLAG_NEG_BEFORE.test(clauseBefore(text, m.index))) { return m; }
      if (m[0].length === 0) { g.lastIndex += 1; }
    }
    return null;
  }

  var TECH_TITLE = /automat|n8n|zapier|make\.com|make scenario|integromat|\bapi\b|developer|\bdev\b|coder|coding|programm|\bscripts?\b|scripting|airtable|bubble|\bai\b|gpt|openai|chatbot|integration|google (?:sheet|data studio)|databox|dashboard|\bclay\b|clickup|notion|gohighlevel|highlevel|\bghl\b|\bcrm\b|software|web ?site|wordpress|shopify|\bbolt\b|query|workflow|python|javascript|\bsql\b|power bi/i;

  var RE = {
    aboutRating: /^(\d(?:\.\d+)?) of ([\d,]+) reviews?$/i,
    aboutRatingAlt: /^Rating is (\d(?:\.\d+)?) out of 5\.?$/i,
    noReviews: /^No reviews yet/i,
    cityTime: /^(.*?)(\d{1,2}:\d{2}\s?[AP]M)$/,
    jobsPosted: /^([\d,]+) jobs? posted/i,
    hireRate: /^(\d+)% hire rate(?:,\s*([\d,]+) open jobs?)?/i,
    totalSpent: /^\$([\d,.]+)\s*([KkMm])?\+?\s*total spent/i,
    hires: /^([\d,]+) hires?(?:,\s*([\d,]+) active)?/i,
    avgHourly: /^\$([\d,.]+)\s*\/hr avg hourly rate paid/i,
    hours: /^([\d,]+) hours?$/i,
    companySize: /company \(|people\)|^Individual client|^Large company|^Enterprise/i,
    memberSince: /^Member since (.+)$/i,
    historyHead: /^Client(?:'|\u2019)s recent history(?: \((\d+)\))?/i,
    historyEnd: /^(Other open jobs by this Client|Footer navigation|Similar jobs on Upwork|Explore similar jobs)/i,
    skipLine: /^(Jobs in progress|Completed jobs|View more.*|Show more.*|Load more.*)$/i,
    ratingLine: /^Rating is (\d(?:\.\d+)?) out of 5\.?$/i,
    numberOnly: /^\d(?:\.\d+)?$/,
    noFeedback: /^No feedback given$/i,
    toFreelancer: /^To freelancer:\s*(.*?)\s*(No feedback given)?$/i,
    dateRange: /^[A-Z][a-z]{2,8}\.? \d{4}\s*-\s*(?:[A-Z][a-z]{2,8}\.? \d{4}|Present)$/,
    hourlyPay: /^([\d,.]+) hrs? @ \$([\d,.]+)\s*\/\s*hr$/i,
    fixedPay: /^Fixed-price(?:\s*\$([\d,.]+))?$/i,
    billed: /^Billed:\s*\$([\d,.]+)/i
  };

  function num(s) {
    if (s === undefined || s === null || s === "") { return null; }
    var v = parseFloat(String(s).replace(/,/g, ""));
    return isNaN(v) ? null : v;
  }

  function round(v, d) {
    if (v === null || v === undefined || isNaN(v)) { return null; }
    var f = Math.pow(10, d || 0);
    return Math.round(v * f) / f;
  }

  function quantile(values, q) {
    if (!values.length) { return null; }
    var s = values.slice().sort(function (a, b) { return a - b; });
    var pos = (s.length - 1) * q;
    var lo = Math.floor(pos);
    var hi = Math.ceil(pos);
    return s[lo] + (s[hi] - s[lo]) * (pos - lo);
  }

  function cleanComment(s) {
    return s.replace(/\s*(?:\u2026|\.\.\.)\s*more$/i, "...").replace(/\s+/g, " ").trim();
  }

  function clip(s, n) {
    if (s.length <= n) { return s; }
    return s.slice(0, n - 3).replace(/\s+\S*$/, "") + "...";
  }

  function parseAbout(lines) {
    var a = {
      rating: null, reviews: null, payment_verified: null, phone_verified: null,
      badges: [], country: null, city: null, jobs_posted: null, hire_rate_pct: null,
      open_jobs: null, total_spent_usd: null, hires: null, active: null,
      avg_hourly_paid: null, hours: null, industry: null, company_size: null,
      member_since: null
    };
    var statIdx = {};
    var m;
    for (var i = 0; i < lines.length; i++) {
      var l = lines[i];
      if ((m = RE.aboutRating.exec(l))) { a.rating = num(m[1]); a.reviews = num(m[2]); statIdx[i] = 1; continue; }
      if ((m = RE.aboutRatingAlt.exec(l))) { a.rating = num(m[1]); statIdx[i] = 1; continue; }
      if (RE.noReviews.test(l)) { a.reviews = 0; statIdx[i] = 1; continue; }
      if (/^Payment (?:method )?verified$/i.test(l)) { a.payment_verified = true; statIdx[i] = 1; continue; }
      if (/^Payment (?:method )?(?:not verified|unverified)/i.test(l)) { a.payment_verified = false; statIdx[i] = 1; continue; }
      if (/^Phone number verified$/i.test(l)) { a.phone_verified = true; statIdx[i] = 1; continue; }
      if (/^Phone number (?:not verified|unverified)/i.test(l)) { a.phone_verified = false; statIdx[i] = 1; continue; }
      if ((m = RE.cityTime.exec(l))) {
        a.city = m[1].trim() || null;
        if (i > 0 && !statIdx[i - 1]) { a.country = lines[i - 1]; statIdx[i - 1] = 1; }
        statIdx[i] = 1; continue;
      }
      if ((m = RE.jobsPosted.exec(l))) { a.jobs_posted = num(m[1]); statIdx[i] = 1; continue; }
      if ((m = RE.hireRate.exec(l))) { a.hire_rate_pct = num(m[1]); a.open_jobs = num(m[2]); statIdx[i] = 1; continue; }
      if ((m = RE.totalSpent.exec(l))) {
        var v = num(m[1]);
        var unit = (m[2] || "").toUpperCase();
        a.total_spent_usd = round(v * (unit === "K" ? 1000 : unit === "M" ? 1000000 : 1), 0);
        statIdx[i] = 1; continue;
      }
      if ((m = RE.hires.exec(l))) { a.hires = num(m[1]); a.active = num(m[2]); statIdx[i] = 1; continue; }
      if ((m = RE.avgHourly.exec(l))) { a.avg_hourly_paid = num(m[1]); statIdx[i] = 1; continue; }
      if ((m = RE.hours.exec(l))) { a.hours = num(m[1]); statIdx[i] = 1; continue; }
      if (RE.companySize.test(l)) { a.company_size = l; statIdx[i] = 1; continue; }
      if ((m = RE.memberSince.exec(l))) { a.member_since = m[1]; statIdx[i] = 1; continue; }
    }
    // Badges: short leftover lines before the location line ("Pays on time",
    // "Experienced client"). Industry: the leftover line right before the
    // company size (or member since) line.
    var locIdx = -1;
    for (var j = 0; j < lines.length; j++) { if (RE.cityTime.test(lines[j])) { locIdx = j; break; } }
    for (var k = 0; k < lines.length; k++) {
      if (statIdx[k]) { continue; }
      var line = lines[k];
      if (/^(Job link|Copy link)$/i.test(line)) { continue; }
      if (locIdx === -1 || k < locIdx - 1) {
        if (line.length <= 40) { a.badges.push(line); }
      } else if (k > locIdx) {
        var nextStat = lines[k + 1] || "";
        if (a.industry === null && (RE.companySize.test(nextStat) || RE.memberSince.test(nextStat) || k === lines.length - 1 || /^Job link/i.test(nextStat))) {
          a.industry = line;
        }
      }
    }
    return a;
  }

  function parseRating(lines, i) {
    // returns [rating or null, next index, gaveFeedback]
    var m = RE.ratingLine.exec(lines[i] || "");
    if (m) {
      var next = i + 1;
      if (RE.numberOnly.test(lines[next] || "")) { next += 1; }
      return [num(m[1]), next, true];
    }
    if (RE.noFeedback.test(lines[i] || "")) { return [null, i + 1, false]; }
    return [null, i, false];
  }

  function parseRecord(block, pay) {
    // block: lines from title through the date line (payment lines excluded)
    var r = {
      title: block[0] || "", fl_rating: null, fl_comment: "", freelancer: null,
      client_rating: null, client_comment: "", hourly_rate: null, hours: null,
      billed: null, fixed_price: null, is_fixed: false
    };
    var tIdx = -1;
    for (var i = 1; i < block.length; i++) { if (/^To freelancer:/i.test(block[i])) { tIdx = i; break; } }
    var end = block.length;
    if (end > 1 && RE.dateRange.test(block[end - 1])) { end -= 1; }
    if (tIdx > 0) {
      var pr = parseRating(block, 1);
      r.fl_rating = pr[0];
      r.fl_comment = cleanComment(block.slice(pr[1], tIdx).join(" "));
      var tm = RE.toFreelancer.exec(block[tIdx]);
      r.freelancer = tm ? tm[1] : null;
      if (tm && tm[2]) {
        r.client_comment = cleanComment(block.slice(tIdx + 1, end).join(" "));
      } else {
        var cr = parseRating(block, tIdx + 1);
        r.client_rating = cr[0];
        r.client_comment = cleanComment(block.slice(cr[1], end).join(" "));
      }
    }
    var hm = RE.hourlyPay.exec(pay[0]);
    if (hm) {
      r.hours = num(hm[1]);
      r.hourly_rate = num(hm[2]);
      var bm = pay[1] ? RE.billed.exec(pay[1]) : null;
      r.billed = bm ? num(bm[1]) : null;
    } else {
      var fm = RE.fixedPay.exec(pay[0]);
      r.is_fixed = true;
      r.fixed_price = fm && fm[1] ? num(fm[1]) : null;
    }
    return r;
  }

  function parseHistory(lines) {
    var records = [];
    var block = [];
    for (var i = 0; i < lines.length; i++) {
      var l = lines[i];
      if (RE.skipLine.test(l)) { continue; }
      if (RE.hourlyPay.test(l) || RE.fixedPay.test(l)) {
        var pay = [l];
        if (i + 1 < lines.length && RE.billed.test(lines[i + 1])) { pay.push(lines[i + 1]); i += 1; }
        if (block.length) { records.push(parseRecord(block, pay)); }
        block = [];
        continue;
      }
      block.push(l);
    }
    return records;
  }

  // Every word of a freelancer's display name ("Muhammad Ahmed K." gives
  // muhammad, ahmed), lowercased: a sign-off "Regards, Ahmed" is theirs.
  function nameTokens(full) {
    if (!full) { return []; }
    return full.split(/[^\p{L}\p{M}'-]+/u).map(function (w) { return w.replace(/^['-]+|['-]+$/g, "").toLowerCase(); })
      .filter(function (w) { return w.length >= 2; });
  }

  // A name is a capitalised word of 2-20 letters, accents included ("José",
  // "Zoë", NFD combining marks too). It must end where the word ends: the
  // lookahead is Unicode-aware, unlike \b, which is ASCII-only in JS and cut
  // "José" to "Jos". A possessive "'s" may follow ("for Jessica's channel").
  var NAME = "(\\p{Lu}[\\p{Ll}\\p{M}]{1,19})(?![\\p{L}\\p{M}])";
  var NOT_AFTER_LETTER = "(?<![\\p{L}\\p{M}])";
  // [pattern, kind]: "address" = the freelancer speaks TO the person
  // ("Thanks José", "Thank you for the opportunity, Jordan."); "about" = talks
  // about them ("working with Casey", "Casey was great").
  var NAME_PATTERNS = [
    [new RegExp(NOT_AFTER_LETTER + "(?:[Ww]ith|[Ff]or) " + NAME, "gud"), "about"],
    [new RegExp(NOT_AFTER_LETTER + "(?:[Tt]hanks|[Tt]hank [Yy]ou|[Tt]hx),?\\s+" + NAME, "gud"), "address"],
    [new RegExp(NOT_AFTER_LETTER + "(?:[Tt]hanks|[Tt]hank [Yy]ou)[^.!?]{0,60},\\s*" + NAME, "gud"), "address"],
    [new RegExp(NOT_AFTER_LETTER + NAME + " (?:was|is|has|had|provided|gave|made|knows|explained|responded)\\b", "gud"), "about"],
    [new RegExp(",\\s*" + NAME + "\\s*[.!]", "gud"), "address"]
  ];
  var HONORIFICS = "(?:[Mm]r|[Mm]rs|[Mm]s|[Mm]x|Miss|Mister|[Dd]r|[Pp]rof|Sir|Madam|Madame)";
  var HONORIFIC_BEFORE = new RegExp("(?<![\\p{L}\\p{M}])" + HONORIFICS + "\\.?\\s*$", "u");
  var CAP_WORD = "(\\p{Lu}[\\p{L}\\p{M}]{1,30})(?![\\p{L}\\p{M}])";
  // "Brightpath team", "Acme Holdings, Inc.": the word before a company suffix
  var COMPANY_AFTER = new RegExp(CAP_WORD + ",?\\s+(?:[Tt]eam|[Ii]nc|INC|LLC|[Ll]lc|LLP|[Ll]td|LTD|Co|CO|[Cc]orp|" +
    "[Cc]orporation|[Gg]roup|[Aa]gency|[Ss]tudios?|[Ll]abs?|[Mm]edia|[Ss]olutions|[Hh]oldings|[Ee]nterprises|GmbH|" +
    "[Cc]ompany)(?![\\p{L}\\p{M}-])", "gu");
  // "Lumora is a great company to work for" (not "a great business owner")
  var COMPANY_IS = new RegExp(CAP_WORD + " (?:is|was) (?:an? |the )(?:[\\p{L}-]+ ){0,2}(?:company|business|agency|" +
    "firm|brand|organi[sz]ation|startup|platform|product|tool|app)(?![\\p{L}\\p{M}-])" +
    "(?! (?:owner|partner|person|player|leader|coach|founder|man|woman|guy|mind))", "gu");
  var HONORIFIC_NAME = new RegExp("(?<![\\p{L}\\p{M}])" + HONORIFICS + "\\.?\\s+" + CAP_WORD, "gu");
  // "Priya was our designer": the freelancer's own teammate
  var TEAMMATE_AFTER = /^(?:['’]s)?\s*(?:,\s*|\s(?:is|was)\s+)(?:our|my)\b/i;
  var PERSON_PRONOUN = /\b(?:he|she|him|her|his|hers|he's|she's|himself|herself)\b/i;

  function wordSet(texts, re) {
    var out = {};
    texts.forEach(function (t) {
      var g = globalRe(re);
      var m;
      while ((m = g.exec(t))) { out[m[1].toLowerCase()] = true; }
    });
    return out;
  }

  // Names freelancers call the client by, counted once per comment. Returns
  // up to 8 {name, count, person}: person is true when at least one mention
  // addresses them directly, or a comment naming only them also says he/she.
  // Never a name that is: a stopword (forms of address, sign-offs, company
  // suffixes, review nouns, tool/brand names, US states); any word of any job
  // title in the history (tool names live there); a word written in lower
  // case anywhere in the history; any word of a freelancer's display name; a
  // word after Mr/Mrs/Ms/Dr/Sir/Madam (a surname); a word followed by a
  // company suffix ("team", "Inc", "LLC", "Agency", ...); a teammate ("Priya
  // was our designer").
  function extractNames(records, flTokens) {
    var vocab = {}, titleWords = {};
    records.forEach(function (r) {
      (r.fl_comment + " " + r.client_comment + " " + r.title).split(/[^\p{L}\p{M}']+/u).forEach(function (w) {
        if (w && w === w.toLowerCase()) { vocab[w] = true; }
      });
      r.title.split(/[^\p{L}\p{M}]+/u).forEach(function (w) { if (w) { titleWords[w.toLowerCase()] = true; } });
    });
    var comments = records.map(function (r) { return r.fl_comment; }).filter(function (c) { return !!c; });
    var companies = wordSet(comments, COMPANY_AFTER);
    var companiesIs = wordSet(comments, COMPANY_IS);
    var surnames = wordSet(comments, HONORIFIC_NAME);
    function banned(low) {
      return STOPWORDS[low] || vocab[low] || titleWords[low] || flTokens[low] || companies[low] ||
        companiesIs[low] || surnames[low];
    }
    var counts = {}, person = {};
    comments.forEach(function (text) {
      var seen = {}, addressed = {};
      NAME_PATTERNS.forEach(function (pk) {
        var re = pk[0];
        re.lastIndex = 0;
        var m;
        while ((m = re.exec(text))) {
          var n = m[1];
          var at = m.indices[1][0];
          var low = n.toLowerCase();
          if (banned(low)) { continue; }
          if (HONORIFIC_BEFORE.test(text.slice(Math.max(0, at - 12), at))) { continue; }
          if (TEAMMATE_AFTER.test(text.slice(m.indices[1][1], m.indices[1][1] + 20))) { continue; }
          seen[n] = true;
          if (pk[1] === "address") { addressed[n] = true; }
        }
      });
      var here = Object.keys(seen);
      here.forEach(function (n) {
        counts[n] = (counts[n] || 0) + 1;
        if (addressed[n] || (here.length === 1 && PERSON_PRONOUN.test(text))) { person[n] = true; }
      });
    });
    return Object.keys(counts).map(function (n) { return { name: n, count: counts[n], person: !!person[n] }; })
      .sort(function (a, b) { return b.count - a.count || (a.name < b.name ? -1 : 1); })
      .slice(0, 8);
  }

  // how many history records the page text holds right now (the expander
  // stops when a click adds none)
  function historyCount(text) {
    var sec = sections(text);
    return sec.histStart === -1 ? 0 : parseHistory(sec.lines.slice(sec.histStart + 1, sec.histEnd)).length;
  }

  function snippetAround(text, m) {
    if (!m) { return clip(text, 110); }
    var start = Math.max(0, m.index - 50);
    var s = text.slice(start, m.index + m[0].length + 50).trim();
    return (start > 0 ? "..." : "") + clip(s, 110);
  }

  function avg(values) {
    if (!values.length) { return null; }
    return values.reduce(function (a, b) { return a + b; }, 0) / values.length;
  }

  function compact(obj) {
    function walk(v) {
      if (typeof v === "string") { return v.length > LIMITS.str ? v.slice(0, LIMITS.str) : v; }
      if (Array.isArray(v)) { return v.slice(0, LIMITS.arr).map(walk); }
      if (v && typeof v === "object") {
        var o = {};
        Object.keys(v).forEach(function (k) { o[k] = walk(v[k]); });
        return o;
      }
      return v;
    }
    var out = walk(obj);
    var shrinkable = ["fl_quotes", "client_voice", "red_flags", "names", "about.badges"];
    var guard = 0;
    while (JSON.stringify(out).length > LIMITS.json && guard < 60) {
      guard += 1;
      for (var i = 0; i < shrinkable.length; i++) {
        var path = shrinkable[i].split(".");
        var holder = path.length === 2 ? out[path[0]] : out;
        var key = path[path.length - 1];
        if (holder && Array.isArray(holder[key]) && holder[key].length) { holder[key].pop(); break; }
      }
    }
    return out;
  }

  function sections(text) {
    var lines = String(text || "").split(/\r?\n/).map(function (l) { return l.replace(/\s+/g, " ").trim(); })
      .filter(function (l) { return l.length > 0; });
    var aboutStart = -1, histStart = -1, histEnd = lines.length, claimed = null;
    for (var i = 0; i < lines.length; i++) {
      if (aboutStart === -1 && /^About the client$/i.test(lines[i])) { aboutStart = i; }
      var hm = RE.historyHead.exec(lines[i]);
      if (histStart === -1 && hm) { histStart = i; claimed = hm[1] ? num(hm[1]) : null; }
    }
    var aboutEnd = histStart !== -1 ? histStart : lines.length;
    for (var j = Math.max(aboutStart, 0); j < lines.length; j++) {
      if (RE.historyEnd.test(lines[j]) && j > aboutStart) { if (histStart === -1) { aboutEnd = Math.min(aboutEnd, j); } break; }
    }
    if (histStart !== -1) {
      for (var k = histStart + 1; k < lines.length; k++) { if (RE.historyEnd.test(lines[k])) { histEnd = k; break; } }
    }
    return { lines: lines, aboutStart: aboutStart, aboutEnd: aboutEnd, histStart: histStart, histEnd: histEnd, claimed: claimed };
  }

  function parseClientIntel(text) {
    var sec = sections(text);
    var lines = sec.lines, aboutStart = sec.aboutStart, aboutEnd = sec.aboutEnd;
    var histStart = sec.histStart, histEnd = sec.histEnd, claimed = sec.claimed;
    var about = aboutStart === -1 ? parseAbout([]) : parseAbout(lines.slice(aboutStart + 1, aboutEnd));
    var records = histStart === -1 ? [] : parseHistory(lines.slice(histStart + 1, histEnd));

    var flTokens = {}, flPeople = {};
    records.forEach(function (r) {
      var t = nameTokens(r.freelancer);
      t.forEach(function (w) { flTokens[w] = true; });
      if (t.length) { flPeople[t[0]] = true; }
    });

    var flRatings = records.map(function (r) { return r.fl_rating; }).filter(function (v) { return v !== null; });
    var clRatings = records.map(function (r) { return r.client_rating; }).filter(function (v) { return v !== null; });

    // red flags: only in freelancers' comments about the client
    var redFlags = [], flagged = 0, flaggedLow = 0;
    records.forEach(function (r) {
      if (!r.fl_comment) { return; }
      var hit = null;
      var at = null;
      for (var f = 0; f < RED_FLAGS.length; f++) {
        at = flagMatch(r.fl_comment, RED_FLAGS[f][1]);
        if (at) { hit = RED_FLAGS[f]; break; }
      }
      if (!hit) { return; }
      flagged += 1;
      if (r.fl_rating === null || r.fl_rating < 4.5) { flaggedLow += 1; }
      if (redFlags.length < 5) { redFlags.push({ k: hit[0], r: r.fl_rating, t: snippetAround(r.fl_comment, at) }); }
    });

    var praise = {};
    PRAISE.forEach(function (p) {
      praise[p[0]] = records.filter(function (r) { return r.fl_comment && praiseHit(r.fl_comment, p[1]); }).length;
    });

    var hourly = records.filter(function (r) { return r.hourly_rate !== null; });
    var hourlyRates = hourly.map(function (r) { return r.hourly_rate; });
    var fixedPrices = records.filter(function (r) { return r.is_fixed && r.fixed_price !== null; }).map(function (r) { return r.fixed_price; });
    var contractValues = records.map(function (r) {
      if (r.hourly_rate !== null) { return r.billed !== null ? r.billed : (r.hours !== null ? r.hours * r.hourly_rate : null); }
      return r.fixed_price;
    }).filter(function (v) { return v !== null; });
    var techRates = hourly.filter(function (r) { return TECH_TITLE.test(r.title); }).map(function (r) { return r.hourly_rate; });

    var rates = {
      hourly_median: round(quantile(hourlyRates, 0.5), 2), hourly_n: hourlyRates.length,
      fixed_median: round(quantile(fixedPrices, 0.5), 2), fixed_n: fixedPrices.length,
      contract_median: round(quantile(contractValues, 0.5), 2), contracts_n: contractValues.length,
      share_le_20: contractValues.length ? round(contractValues.filter(function (v) { return v <= 20; }).length / contractValues.length, 2) : null,
      tech_hourly_median: round(quantile(techRates, 0.5), 2),
      tech_hourly_p25: round(quantile(techRates, 0.25), 2),
      tech_hourly_p75: round(quantile(techRates, 0.75), 2),
      tech_hourly_n: techRates.length
    };

    var clientVoice = records.filter(function (r) { return r.client_comment.length >= 15; })
      .slice(0, 3).map(function (r) { return clip(r.client_comment, 120); });

    var flComments = records.filter(function (r) { return r.fl_comment.length >= 15; });
    var flagFirst = flComments.filter(function (r) { return RED_FLAGS.some(function (f) { return flagMatch(r.fl_comment, f[1]); }); });
    var rest = flComments.filter(function (r) { return flagFirst.indexOf(r) === -1; })
      .sort(function (a, b) { return b.fl_comment.length - a.fl_comment.length; });
    var flQuotes = flagFirst.concat(rest).slice(0, 4).map(function (r) { return clip(r.fl_comment, 140); });

    return compact({
      v: 1,
      about: about,
      history_claimed: claimed,
      history_parsed: records.length,
      names: extractNames(records, flTokens),
      freelancer_names: Object.keys(flPeople).length,
      fl_rating_avg: round(avg(flRatings), 2),
      fl_ratings_n: flRatings.length,
      client_rating_given_avg: round(avg(clRatings), 2),
      client_ratings_n: clRatings.length,
      harsh_ratings_given: clRatings.filter(function (v) { return v < 4.5; }).length,
      red_flags: redFlags,
      red_flag_comments: flagged,
      red_flag_comments_low_rated: flaggedLow,
      praise: praise,
      rates: rates,
      client_voice: clientVoice,
      fl_quotes: flQuotes
    });
  }

  async function runInPage() {
    var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
    var bodyText = function () { return (document.body && document.body.innerText) || ""; };
    var t0 = Date.now();
    while (!/About the client/i.test(bodyText()) && Date.now() - t0 < 25000) { await sleep(500); }
    if (!/About the client/i.test(bodyText())) {
      var challenge = /Just a moment|Verify you are human|cf-challenge|challenge-platform/i.test(document.title + " " + bodyText().slice(0, 400));
      return { v: 1, error: challenge ? "challenge" : "about_not_found", title: String(document.title).slice(0, 120), url: String(location.href).slice(0, 300) };
    }
    function findHeading(re) {
      var els = document.querySelectorAll("h1,h2,h3,h4,h5,h6,header,section,div,span");
      for (var i = 0; i < els.length; i++) {
        var el = els[i];
        if (el.children.length <= 3 && re.test((el.textContent || "").trim())) { return el; }
      }
      return null;
    }
    function visible(el) { return !!(el.offsetParent || (el.getClientRects && el.getClientRects().length)); }
    function attr(el, k) { return el.getAttribute ? el.getAttribute(k) : (el[k] === undefined ? null : el[k]); }
    // An element that would navigate: an <a> (or anything) with a real href,
    // or one inside such a link. Only buttons, role=button elements and
    // anchors without a real href are ever clicked.
    function navigates(el) {
      var href = attr(el, "href");
      if (href && !/^\s*(?:#|javascript:)/i.test(String(href))) { return true; }
      var tag = String(el.tagName || el.tag || "").toLowerCase();
      if (tag === "a" && href === null && el.href) { return true; }
      var link = el.closest ? el.closest("a[href]") : null;
      return !!(link && link !== el && !/^\s*(?:#|javascript:)/i.test(String(attr(link, "href"))));
    }
    function after(a, b) { return !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING); }
    function before(a, b) { return !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_PRECEDING); }
    // Bounds: after the history heading; before the first end marker the
    // parser also stops at (Other open jobs, footer, Similar jobs, Explore
    // similar jobs) when the page has one; inside the history section's
    // container when that container holds a candidate.
    function findViewMore() {
      var head = findHeading(RE.historyHead);
      if (!head) { return null; }
      var tail = null;
      var ends = document.querySelectorAll("h1,h2,h3,h4,h5,h6,header,section,div,span,footer,nav");
      for (var e = 0; e < ends.length; e++) {
        var el = ends[e];
        if (el.children && el.children.length <= 3 && RE.historyEnd.test((el.textContent || "").trim()) && after(head, el)) {
          tail = el; break;
        }
      }
      var box = head.closest ? head.closest("section") : null;
      var cands = document.querySelectorAll("button, a, [role=button]");
      var inBox = null, bounded = null;
      for (var i = 0; i < cands.length; i++) {
        var b = cands[i];
        var t = (b.innerText || b.textContent || "").trim();
        if (!/^View more/i.test(t) || !visible(b) || b.disabled || navigates(b)) { continue; }
        if (!after(head, b)) { continue; }
        if (tail && !before(tail, b)) { continue; }
        if (box && box.contains && box.contains(b)) { inBox = inBox || b; }
        bounded = bounded || b;
      }
      return inBox || bounded;
    }
    // Click, wait, and stop as soon as a click adds no history record (one
    // extra wait for a slow load first).
    var clicks = 0;
    var have = historyCount(bodyText());
    for (var n = 0; n < 15; n++) {
      var btn = findViewMore();
      if (!btn) { break; }
      btn.click();
      clicks += 1;
      await sleep(1500);
      var now = historyCount(bodyText());
      if (now <= have) { await sleep(1500); now = historyCount(bodyText()); }
      if (now <= have) { break; }
      have = now;
    }
    var text = bodyText();
    var start = text.search(/About the client/i);
    var out = parseClientIntel(start >= 0 ? text.slice(start) : text);
    out.expand_clicks = clicks;
    out.url = String(location.href).split("?")[0].slice(0, 200);
    return compact(out);
  }

  return { parseClientIntel: parseClientIntel, runInPage: runInPage, compact: compact, LIMITS: LIMITS };
})();
if (typeof module !== "undefined" && module.exports) { module.exports = __clientIntel; }
// Auto-run when pasted whole; the loader sets __ADVERO_CI_NO_AUTORUN and calls runInPage() itself.
await (typeof document !== "undefined" && typeof __ADVERO_CI_NO_AUTORUN === "undefined" ? __clientIntel.runInPage() : Promise.resolve(null));
