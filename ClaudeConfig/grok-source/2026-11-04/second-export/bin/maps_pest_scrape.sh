#!/usr/bin/env bash
# maps_pest_scrape.sh - free Google Maps -> pest control lead CSV (gosom/google-maps-scraper, no API keys)
# Usage: maps_pest_scrape.sh CITY_LIST_FILE [OUT_TAG]
#   CITY_LIST_FILE: one "City, ST" per line (# comments ok)
#   OUT_TAG: output name suffix (default YYYYMMDD) -> ~/advero/state/leads/maps/pest_<OUT_TAG>.csv
# Env overrides (safe defaults - see README):
#   MAX_CITIES=10   cities taken per run (next undone cities from the list; progress in maps/state/)
#   DEPTH=6         scroll depth per query (~60-70 places/query; Google caps a list at ~120)
#   CONC=1          scraper concurrency (keep 1)
#   QUERY_TERMS="pest control|exterminator|termite control"
#   EMAIL_WORKERS=6 parallel websites for the email crawl (one request at a time per site)
#   MAX_PLACES=2000 hard stop on raw places per run
set -euo pipefail
CITY_FILE="${1:?usage: maps_pest_scrape.sh CITY_LIST_FILE [OUT_TAG]}"
TAG="${2:-$(date +%Y%m%d)}"
MAX_CITIES="${MAX_CITIES:-10}"; DEPTH="${DEPTH:-6}"; CONC="${CONC:-1}"
QUERY_TERMS="${QUERY_TERMS:-pest control|exterminator|termite control}"
EMAIL_WORKERS="${EMAIL_WORKERS:-6}"; MAX_PLACES="${MAX_PLACES:-2000}"
BIN="$HOME/advero/opt/google-maps-scraper"
BASE="$HOME/advero/state/leads/maps"; RAW="$BASE/raw"; LOGS="$BASE/logs"; STATE="$BASE/state"
mkdir -p "$RAW" "$LOGS" "$STATE"
OUT="$BASE/pest_${TAG}.csv"; LOG="$LOGS/pest_${TAG}.log"
DONE="$STATE/cities_done_$(basename "$CITY_FILE" .txt).txt"; touch "$DONE"
exec 9>"$STATE/maps_pest_scrape.lock"; flock -n 9 || { echo "another run is active, exiting"; exit 0; }
[ -x "$BIN" ] || { echo "scraper binary missing at $BIN (see README: build from source)"; exit 2; }

# Pick next undone cities
mapfile -t CITIES < <(grep -v '^\s*#' "$CITY_FILE" | sed '/^\s*$/d' | grep -vxF -f "$DONE" | head -n "$MAX_CITIES" || true)
[ "${#CITIES[@]}" -gt 0 ] || { echo "all cities in $CITY_FILE done"; exit 0; }
Q="$RAW/queries_${TAG}.txt"; : > "$Q"
IFS='|' read -ra TERMS <<< "$QUERY_TERMS"
for c in "${CITIES[@]}"; do for t in "${TERMS[@]}"; do echo "$t in $c #!#${c}|${t}" >> "$Q"; done; done
echo "$(date '+%F %T %Z') start tag=$TAG cities=${#CITIES[@]} queries=$(wc -l < "$Q") depth=$DEPTH c=$CONC" | tee -a "$LOG"
START=$(date +%s)

# 1) Google Maps listing scrape (no -email: browser email crawl is slow/timeouts; we use a light crawler below)
MAPS_RAW="$RAW/pest_${TAG}_raw.csv"
timeout 3h "$BIN" -input "$Q" -results "$MAPS_RAW" -depth "$DEPTH" -c "$CONC" -exit-on-inactivity 3m >> "$LOG" 2>&1 || echo "scraper exit $?" | tee -a "$LOG"
MAPS_END=$(date +%s)
NPLACES=$(python3 -c "import csv,sys;csv.field_size_limit(10**9);print(sum(1 for _ in csv.DictReader(open('$MAPS_RAW'))))" 2>/dev/null || echo 0)
NQ=$(wc -l < "$Q"); NFOUND=$(grep -c 'places found' "$LOG" || true); NZERO=$(grep -c '"0 places found"' "$LOG" || true)
# 2) Throttle / block check - stop, do not retry or evade
if grep -qiE 'google\.com/sorry|unusual traffic|recaptcha' "$LOG" || { [ "$NQ" -ge 4 ] && [ "$NPLACES" -lt 5 ]; } || [ "$NZERO" -ge 3 ]; then
  echo "$(date '+%F %T') THROTTLE/BLOCK SUSPECTED (places=$NPLACES zero_queries=$NZERO). Stopping; cities NOT marked done. Wait 24h+ and lower MAX_CITIES/DEPTH." | tee -a "$LOG"
  exit 3
fi
if [ "$NPLACES" -gt "$MAX_PLACES" ]; then echo "note: $NPLACES places > MAX_PLACES=$MAX_PLACES; lower MAX_CITIES next time" | tee -a "$LOG"; fi
# 3) Polite website email crawl
python3 "$HOME/advero/bin/site_email_crawl.py" "$MAPS_RAW" "$RAW/pest_${TAG}_raw_emails.csv" --workers "$EMAIL_WORKERS" >> "$LOG" 2>&1
python3 "$HOME/advero/bin/site_email_crawl.py" "$RAW/pest_${TAG}_raw_emails.csv" "$RAW/pest_${TAG}_raw_emails.csv" --workers 3 --retry-status fetch_error,error >> "$LOG" 2>&1 || true
# 4) Normalize + dedupe vs final-leads, pool pest files and earlier maps outputs (domain + email)
python3 "$HOME/advero/bin/maps_postprocess.py" "$RAW/pest_${TAG}_raw_emails.csv" "$OUT" --stats "$LOGS/pest_${TAG}_stats.json" | tee -a "$LOG"
printf '%s\n' "${CITIES[@]}" >> "$DONE"
END=$(date +%s)
echo "$(date '+%F %T %Z') done places=$NPLACES maps_s=$((MAPS_END-START)) total_s=$((END-START)) out=$OUT" | tee -a "$LOG"
echo "$(date -Iseconds),$TAG,${#CITIES[@]},$NPLACES,$((END-START)),$OUT" >> "$STATE/runs.csv"
