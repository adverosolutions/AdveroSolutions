@direction LR
@spacing 60

[1 - A student or parent asks the bot a question on your website or social page] -> [2 - The bot answers from your own program details, dates and prices]
[2 - The bot answers from your own program details, dates and prices] -> [3 - It asks a few questions to learn the student's grade, goals and start date]
[3 - It asks a few questions to learn the student's grade, goals and start date] -> {4 - Does the question need a real person, like a complaint or a special case?}
{4 - Does the question need a real person, like a complaint or a special case?} -> "Yes" -> [4b - If it does, the bot hands the chat to your team and tells them why]
{4 - Does the question need a real person, like a complaint or a special case?} -> "No" -> [5 - If not, the bot offers a call or the next enrollment step and books it]
[4b - If it does, the bot hands the chat to your team and tells them why] -> [6 - The lead and the full chat are sent to your CRM by webhook]
[5 - If not, the bot offers a call or the next enrollment step and books it] -> [6 - The lead and the full chat are sent to your CRM by webhook]
[6 - The lead and the full chat are sent to your CRM by webhook] -> [7 - Your team gets a notification with the details they need for the call]
[7 - Your team gets a notification with the details they need for the call] -> [8 - Before launch, I run test chats through every path and fix what breaks]
[8 - Before launch, I run test chats through every path and fix what breaks] -> [9 - After launch, I update the bot as your programs and dates change]
