@direction LR
@spacing 60

(Weekly Automated Refresh) -> [Split Country List Into One Batch at a Time]
(Weekly Automated Refresh) -> [Split Directory URL List Into One Batch at a Time]
[Split Country List Into One Batch at a Time] -> [Query Google Places API for Equine Vets in This Country]
[Query Google Places API for Equine Vets in This Country] -> [Parse Results Into Name, Address, Phone, Website]
[Parse Results Into Name, Address, Phone, Website] -> {More Countries Left to Query?}
{More Countries Left to Query?} --> [Split Country List Into One Batch at a Time]
{More Countries Left to Query?} -> "false" -> [Merge Google Places and Directory Records]
[Split Directory URL List Into One Batch at a Time] -> [Fetch the Directory Page HTML]
[Fetch the Directory Page HTML] -> [Parse HTML and Extract Name, Clinic, Email, Phone]
[Parse HTML and Extract Name, Clinic, Email, Phone] -> [Normalize Directory Fields to Match the Places Schema]
[Normalize Directory Fields to Match the Places Schema] -> {More Directory Pages Left to Parse?}
{More Directory Pages Left to Parse?} --> [Split Directory URL List Into One Batch at a Time]
{More Directory Pages Left to Parse?} -> "false" -> [Merge Google Places and Directory Records]
[Merge Google Places and Directory Records] -> [Deduplicate by Name, Country, and Matching Phone or Website]
[Deduplicate by Name, Country, and Matching Phone or Website] -> [[Write Clean Records to Google Sheets]]
[[Write Clean Records to Google Sheets]] -> [Log Run Summary: New, Updated, Duplicates Skipped]
