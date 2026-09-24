"""appointments_tick --no-show-watch: N1 and detection only, for calls that
started in the last 30 minutes; no request at all when no call is on."""
from datetime import datetime, timedelta

import httpx

from shared import job_log
from shared.ghl import GHL
from shared.store import JsonFileStore

from jobs import appointments_tick as tick_mod

START = datetime.fromisoformat("2026-09-23T11:30:00-05:00")
APPT = {
    "id": "appt-watch-1", "contact_id": "c-watch-1", "first_name": "Ilmi", "company": "Shining Armor Cleaning NJ",
    "email": "ilmi@watch.test", "niche": "cleaning", "offer": "reactivation", "lead_tz": "America/New_York",
    "start_iso": START.isoformat(), "end_iso": (START + timedelta(minutes=15)).isoformat(),
    "zoom_link": "https://zoom.us/j/000000000011",
}
HOST = {"at_iso": (START - timedelta(minutes=1)).isoformat(), "name": "Lorenzo Villarreal",
        "email": "lorenzovillarreal@adverosolutions.com", "is_host": True}


class Recorder(object):
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return httpx.Response(200, json={"ok": True})


def test_watch_sends_n1_and_flags_but_never_runs_the_ladder(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    rec = Recorder()
    ghl = GHL(token=None, transport=httpx.MockTransport(rec))
    old = dict(APPT, id="appt-old", start_iso=(START - timedelta(hours=1)).isoformat())
    ahead = dict(APPT, id="appt-ahead", start_iso=(START + timedelta(hours=2)).isoformat())
    joins = {APPT["id"]: [HOST]}

    out = tick_mod.watch(START + timedelta(minutes=5), store, ghl, [APPT, old, ahead], joins_override=joins)
    assert out["checked"] == 1 and out["no_show"][0]["events"] == ["still_on:would_do"]
    assert out["recovery"]["would_do"] == 1

    out = tick_mod.watch(START + timedelta(minutes=10), store, ghl, [APPT], joins_override=joins)
    assert out["no_show"][0]["events"] == ["no_show"]
    # S+25: the reschedule email is due, but the watch leaves it to the regular tick
    out = tick_mod.watch(START + timedelta(minutes=25), store, ghl, [APPT], joins_override=joins)
    assert out["recovery"]["would_do"] == 0
    assert [r["payload"]["subject"] for r in job_log.read_shadow_log() if r["action"] == "send_message"] == ["I'm on"]
    assert rec.requests == []


def test_watch_candidates_come_from_store_keys_only(tmp_env):
    store = JsonFileStore(tmp_env / "s.json")
    store.set("showrate:appt-now:%s" % START.isoformat(), {"touches": []})
    store.set("showrate:appt-old:%s" % (START - timedelta(hours=2)).isoformat(), {"touches": []})
    assert tick_mod.watch_candidates(store, START + timedelta(minutes=5)) == ["appt-now"]
    assert tick_mod.watch_candidates(store, START - timedelta(minutes=5)) == []


def test_a_watch_run_with_no_call_on_does_nothing(tmp_env, monkeypatch):
    logged = []
    monkeypatch.setattr(job_log, "log_run", lambda *a, **k: logged.append(a))

    def no_read(*a, **k):
        raise AssertionError("the calendar must not be read when no call is in the window")

    monkeypatch.setattr(tick_mod, "fetch_appointments", no_read)
    rc = tick_mod.main(["--no-show-watch", "--dry-run", "--no-notify", "--quiet",
                        "--now", (START + timedelta(minutes=3)).isoformat(), "--store", str(tmp_env / "empty.json")])
    assert rc == 0 and logged == []
