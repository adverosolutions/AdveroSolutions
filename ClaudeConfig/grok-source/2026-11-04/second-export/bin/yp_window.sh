#!/bin/bash
# yp_window.sh - Yellow Pages nightly window, 2:00 to 5:00 AM CT, never alongside Maps.
# usage: yp_window.sh [TAG]   (default TAG = YYYYMMDD). Run from a 2 AM CT routine.
set -u
TAG=${1:-$(date +%Y%m%d)}
KILL=$HOME/advero/state/KILL_SWITCH; PAUSE=$HOME/advero/state/leads/maps/state/PAUSE_MAPS
YP=$HOME/advero/state/leads/yp; CITIES=$YP/cities/pest_test10.txt; LOG=$YP/logs/yp_window_$TAG.log
mkdir -p $YP/logs $YP/state
log(){ echo "$(date '+%F %T %Z') $*" | tee -a $LOG; }
[ -e $KILL ] && { log "KILL_SWITCH present, not starting"; exit 9; }
[ -e $YP/STOPPED_BLOCK ] && { log "STOPPED_BLOCK marker present ($(cat $YP/STOPPED_BLOCK)); refusing. Remove only after LGM/Lorenzo say so."; exit 3; }
exec 7>$YP/state/yp.lock; flock -n 7 || { log "yp already running"; exit 0; }
CREATED=0; [ -e $PAUSE ] || { touch $PAUSE; CREATED=1; }
cleanup(){ [ $CREATED = 1 ] && rm -f $PAUSE; log "exit, PAUSE_MAPS released (created_by_us=$CREATED)"; }
trap cleanup EXIT; trap 'exit 130' INT TERM HUP
log "PAUSE_MAPS set; waiting for google-maps-scraper to finish"
while pgrep -f google-maps-scraper >/dev/null; do
  [ "$(date +%H%M)" -ge 0450 ] && [ "$(date +%H)" -lt 12 ] && { log "maps still running at 4:50 AM, skipping tonight"; exit 0; }
  sleep 30; done
# also hold the maps flock so a new maps crawl cannot start mid-run
exec 9>$HOME/advero/state/leads/maps/state/maps_pest_scrape.lock; flock -w 600 9 || { log "maps lock busy, skipping"; exit 0; }
while [ "$(date +%H)" -lt 2 ]; do sleep 30; done   # start no earlier than 2:00 AM CT
[ "$(date +%H)" -ge 5 ] && [ "$(date +%H)" -lt 12 ] && { log "past 5 AM, not starting"; exit 0; }
[ -e $KILL ] && { log "KILL_SWITCH present"; exit 9; }
log "start yp_scrape tag=$TAG"
timeout --signal=TERM 3h python3 $HOME/advero/bin/yp_scrape.py --cities $CITIES --tag $TAG --stop-at 05:00 >> $LOG 2>&1; RC=$?
log "yp_scrape exit $RC"
flock -u 9; [ $CREATED = 1 ] && rm -f $PAUSE; CREATED=0; log "PAUSE_MAPS released"
[ $RC = 0 ] && { $HOME/advero/bin/yp_post.sh $TAG >> $LOG 2>&1; log "post exit $?"; }
exit $RC
