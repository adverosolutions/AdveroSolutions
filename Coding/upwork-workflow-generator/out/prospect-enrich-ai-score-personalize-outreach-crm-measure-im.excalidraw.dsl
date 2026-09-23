@direction LR
@spacing 60

(Daily Prospect List Refresh) -> [Pull New Prospects from the Sourcing Tool]
[Pull New Prospects from the Sourcing Tool] -> [Enrich With Firmographic and Intent Data]
[Enrich With Firmographic and Intent Data] -> [Score Fit Against the ICP and Draft Personalized Outreach]
[Score Fit Against the ICP and Draft Personalized Outreach] -> {ICP Fit Score Above Threshold?}
{ICP Fit Score Above Threshold?} -> "true" -> [Send the Personalized Outreach Email]
{ICP Fit Score Above Threshold?} -> "true" -> [Add to a Personalized LinkedIn Sequence]
[Send the Personalized Outreach Email] -> [Log the Prospect and Activity in the CRM]
[Add to a Personalized LinkedIn Sequence] -> [Log the Prospect and Activity in the CRM]
[Log the Prospect and Activity in the CRM] -> [Update Pipeline Stage Based on Engagement]
[Update Pipeline Stage Based on Engagement] -> [Aggregate Reply Rate, Meeting Rate, and Pipeline Generated]
[Aggregate Reply Rate, Meeting Rate, and Pipeline Generated] -> {Reply Rate Below Benchmark?}
{Reply Rate Below Benchmark?} -> "true" -> [Alert: Campaign Underperforming Benchmark]
{Reply Rate Below Benchmark?} -> "false" -> [[Write Metrics to the GTM Performance Dashboard]]
[Alert: Campaign Underperforming Benchmark] -> [[Write Metrics to the GTM Performance Dashboard]]
[GPT-4.1] --> [Score Fit Against the ICP and Draft Personalized Outreach]
