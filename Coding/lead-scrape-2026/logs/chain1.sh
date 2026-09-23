set -u
cd /Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/lead-scrape-2026
BIG12="california|texas|new york|florida|illinois|pennsylvania|michigan|north carolina|virginia|ohio|massachusetts|georgia"
MID10="new jersey|washington|arizona|colorado|minnesota|maryland|indiana|wisconsin|tennessee|missouri"
MID12="oregon|south carolina|connecticut|kentucky|nevada|alabama|louisiana|utah|oklahoma|iowa|kansas|arkansas"
SMALL17="nebraska|new mexico|mississippi|new hampshire|district of columbia|idaho|maine|vermont|rhode island|delaware|west virginia|montana|wyoming|north dakota|south dakota|alaska|hawaii"
SMALL11="maine|vermont|rhode island|delaware|west virginia|montana|wyoming|north dakota|south dakota|alaska|hawaii"
python3 wave4.py bookkeeping__w4mid10 bookkeeping 200 "$MID10" --max-usd=5 &
python3 wave4.py bookkeeping__w4mid12 bookkeeping 120 "$MID12" --max-usd=5 &
wait
python3 wave4.py bookkeeping__w4small17 bookkeeping 60 "$SMALL17" --max-usd=5 &
python3 wave4.py recruiting__w4mid4 recruiting 200 "washington|arizona|colorado|minnesota" --max-usd=5 &
wait
python3 wave4.py recruiting__w4small11 recruiting 50 "$SMALL11" --max-usd=5 &
python3 wave4.py cleaning__w4small11 cleaning 60 "$SMALL11" --max-usd=5 &
wait
python3 wave4.py cleaning_csuite_w4small11 cleaning_csuite 60 "$SMALL11" --max-usd=5 &
python3 wave4.py cleaning_cs_w4a cleaning_cs 60 "$MID10|$MID12" --max-usd=5 &
wait
python3 wave4.py cleaning_cs_w4b cleaning_cs 60 "$SMALL17" --max-usd=5
echo "=== USAGE CHECK 1"; TOK=$(grep '^APIFY_TOKEN=' .env | cut -d= -f2-); curl -s "https://api.apify.com/v2/users/me/limits?token=$TOK" | python3 -c "import json,sys; d=json.load(sys.stdin)['data']; print('monthlyUsageUsd', round(d['current']['monthlyUsageUsd'],2))"
python3 wave4.py recruiting_csuite_w4big12 recruiting 200 "$BIG12" --seniority=c_suite --max-usd=6 &
python3 wave4.py bookkeeping_csuite_w4big12 bookkeeping 200 "$BIG12" --seniority=c_suite --max-usd=6 &
wait
echo "=== USAGE CHECK 2"; curl -s "https://api.apify.com/v2/users/me/limits?token=$TOK" | python3 -c "import json,sys; d=json.load(sys.stdin)['data']; print('monthlyUsageUsd', round(d['current']['monthlyUsageUsd'],2))"
echo "=== CHAIN1 DONE"
