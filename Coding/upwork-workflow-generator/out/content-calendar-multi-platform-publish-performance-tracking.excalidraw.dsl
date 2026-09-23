@direction LR
@spacing 60

(Check for Scheduled Posts Every Hour) -> [[Pull Posts Due to Publish from the Content Calendar]]
[[Pull Posts Due to Publish from the Content Calendar]] -> {Post Marked Approved and Ready?}
{Post Marked Approved and Ready?} -> "true" -> [Publish to Facebook Page]
{Post Marked Approved and Ready?} -> "true" -> [Publish to X · Twitter]
[Publish to Facebook Page] -> [Merge Publish Results Across Platforms]
[Publish to X · Twitter] -> [Merge Publish Results Across Platforms]
[Merge Publish Results Across Platforms] -> {Every Platform Published Successfully?}
{Every Platform Published Successfully?} -> "true" -> [[Log Post URLs and Status Back to the Calendar]]
{Every Platform Published Successfully?} -> "false" -> [Alert: Publish Failed on One or More Platforms]
(Daily Performance Pull) -> [Pull Facebook Post Engagement]
(Daily Performance Pull) -> [Pull X · Twitter Post Metrics]
[Pull Facebook Post Engagement] -> [Aggregate Likes, Comments, Shares, and Clicks by Post]
[Pull X · Twitter Post Metrics] -> [Aggregate Likes, Comments, Shares, and Clicks by Post]
[Aggregate Likes, Comments, Shares, and Clicks by Post] -> [[Write Performance Data Back to the Calendar]]
