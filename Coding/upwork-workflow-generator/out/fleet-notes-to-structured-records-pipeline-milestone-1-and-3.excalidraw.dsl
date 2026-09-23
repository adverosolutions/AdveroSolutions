@direction LR
@spacing 60

(1 - Voice or Text Note From Dispatcher or Driver) -> {2 - Is This an Audio Recording?}
{2 - Is This an Audio Recording?} -> "true" -> [3 - Whisper: Turn the Recording Into Text]
{2 - Is This an Audio Recording?} -> "false" -> [4 - Clean the Note and Attach Truck, Driver and Date]
[3 - Whisper: Turn the Recording Into Text] -> [4 - Clean the Note and Attach Truck, Driver and Date]
[4 - Clean the Note and Attach Truck, Driver and Date] -> [5 - Extraction Model, Cheap: Note Into Structured JSON]
[5 - Extraction Model, Cheap: Note Into Structured JSON] -> [6 - Check the JSON Against the Record Schema]
[6 - Check the JSON Against the Record Schema] -> {7 - Did It Come Back Valid?}
{7 - Did It Come Back Valid?} -> "true" -> [[9 - Save the Record, Row Locked to That Fleet]]
{7 - Did It Come Back Valid?} -> "false" -> [8 - Send It Back With a Repair Prompt, Twice at Most]
[8 - Send It Back With a Repair Prompt, Twice at Most] --> [5 - Extraction Model, Cheap: Note Into Structured JSON]
[[9 - Save the Record, Row Locked to That Fleet]] -> [10 - Hand the Record to the Review Screen]
(11 - Raw Load-Board Text Pasted In) -> [12 - Extraction Model: Pull the Loads Out of Messy Text]
[12 - Extraction Model: Pull the Loads Out of Messy Text] -> [13 - Score Revenue per Mile, Deadhead, 9-Car Unit and Weight Limits]
[13 - Score Revenue per Mile, Deadhead, 9-Car Unit and Weight Limits] -> [14 - Pick the Best Legal Combination for Each Truck]
[14 - Pick the Best Legal Combination for Each Truck] -> [15 - Synthesis Model, Larger: Write the HTML Load Card]
[15 - Synthesis Model, Larger: Write the HTML Load Card] -> [[16 - Save the Scored Loads and the Card]]
(17 - Any Step Fails, Anywhere) -> [18 - Post the Failure With a Link to the Run]
[Provider Adapter: Anthropic / OpenAI / Google] --> [5 - Extraction Model, Cheap: Note Into Structured JSON]
[Force the Schema: Loads, Expenses, Driver Events, Broker Contacts, Maintenance] --> [5 - Extraction Model, Cheap: Note Into Structured JSON]
[Force One Row per Load: Pickup, Drop, Rate, Miles, Vehicles] --> [12 - Extraction Model: Pull the Loads Out of Messy Text]
[Provider Adapter: Same Interface, Bigger Model] --> [15 - Synthesis Model, Larger: Write the HTML Load Card]
