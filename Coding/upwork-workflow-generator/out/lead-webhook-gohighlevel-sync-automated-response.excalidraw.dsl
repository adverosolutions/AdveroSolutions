@direction LR
@spacing 60

(New Lead Submitted) -> [Normalize Name, Phone, Email, and Source]
[Normalize Name, Phone, Email, and Source] -> [Create or Update Contact in GoHighLevel]
[Create or Update Contact in GoHighLevel] -> {Contact Synced Successfully?}
{Contact Synced Successfully?} -> "true" -> [Send Automated Lead-Response Message]
[Send Automated Lead-Response Message] -> [Tag Contact as Auto-Responded]
[Tag Contact as Auto-Responded] -> [Return Success to Webhook Caller]
{Contact Synced Successfully?} -> "false" -> [Alert: GoHighLevel Sync Failed]
