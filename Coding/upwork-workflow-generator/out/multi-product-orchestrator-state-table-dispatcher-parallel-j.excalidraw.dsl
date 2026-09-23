@direction LR
@spacing 60

(AliExpress Link Submitted) -> [Create the Product Record: One Row, One State, One Source of Truth]
[Create the Product Record: One Row, One State, One Source of Truth] -> [[Write the Product to the State Table as Queued]]
(Dispatcher Runs Every Minute) -> [[Read Every Product and Its Current State]]
[[Read Every Product and Its Current State]] -> {What Does This Product Need Next?}
{What Does This Product Need Next?} -> "store setup" -> [Kick Off the Store Build · Supplied Tool]
{What Does This Product Need Next?} -> "creative" -> [Kick Off Creative and Video · Supplied Tool]
{What Does This Product Need Next?} -> "ad deployment" -> [Kick Off Ad Deployment as a Browser Job]
{What Does This Product Need Next?} -> "codex/claude" -> [Codex/Claude Job: Offer Copy, Policy Check, and Product Classification]
[Kick Off the Store Build · Supplied Tool] -> [[Mark the Job Running With a Job Id and Started Time]]
[Kick Off Creative and Video · Supplied Tool] -> [[Mark the Job Running With a Job Id and Started Time]]
[Kick Off Ad Deployment as a Browser Job] -> [[Mark the Job Running With a Job Id and Started Time]]
[Codex/Claude Job: Offer Copy, Policy Check, and Product Classification] -> [[Mark the Job Running With a Job Id and Started Time]]
(Any Job Reports Back: Done, Failed, or Needs a Human) -> {How Did It End?}
{How Did It End?} -> "done" -> [[Advance the Product to Its Next State]]
{How Did It End?} -> "failed" -> {Under the Retry Cap?}
{How Did It End?} -> "needs a human" -> [[Park It as Waiting on Manual Check and Ping the Reviewer]]
{Under the Retry Cap?} -> "true" -> [[Requeue With Backoff, Attempt Count Plus One]]
{Under the Retry Cap?} -> "false" -> [Alert: Product Stuck After 3 Attempts, With the Last Error]
(Nightly Results Pull) -> [Pull Ad Results, Spend, and COGS per Product]
[Pull Ad Results, Spend, and COGS per Product] -> [Classify Each Product: Scale, Iterate, or Kill, With the Reason]
[Classify Each Product: Scale, Iterate, or Kill, With the Reason] -> [[Write the Daily Report per Product]]
[[Write the Daily Report per Product]] -> [Post Winners, Losers, and Anything Waiting on a Human]
[Claude] --> [Codex/Claude Job: Offer Copy, Policy Check, and Product Classification]
[Claude 2] --> [Classify Each Product: Scale, Iterate, or Kill, With the Reason]
