"""D1 round 3, defect 3: the scheduled precall_tick must not push every 5 minutes.

A call marked no-show sits in the proposal window from start+20 minutes to the
end of its day (140 scheduled runs for a noon call). Each run added a
{'skipped': 'no_show'} proposal row, and any proposal row pushed. A skipped row
now pushes once per call; the same error again about once an hour.
"""
from datetime import datetime, timedelta

from jobs import precall_tick as pt
from services.reply_engine import no_show
from shared.settings import TZ
from shared.store import JsonFileStore

START = TZ.localize(datetime(2026, 9, 23, 12, 0))
APPT = {"id": "appt-1", "start_iso": START.isoformat(), "end_iso": (START + timedelta(minutes=30)).isoformat(),
        "email": "pat@example.test", "company": "Pat Co", "contact_id": "c-1"}


def _window_runs(store, result_for):
    """Every */5 scheduled run from start+20 min to 23:55 CT; how many push."""
    runs = pushes = 0
    t = START + timedelta(minutes=20)
    while t <= TZ.localize(datetime(2026, 9, 23, 23, 55)):
        result = result_for(t)
        runs += 1
        if pt.scheduled_push_due(result, False, store, t):
            pushes += 1
        t += timedelta(minutes=5)
    return runs, pushes


def test_a_no_show_call_pushes_once_over_its_whole_proposal_window(tmp_env):
    store = JsonFileStore(tmp_env / "precall_store.json")
    store.set(no_show.state_key("appt-1"), {"state": "no_show", "start_iso": START.isoformat()})
    results = []

    def run(t):
        result = pt.tick(t, store, ghl=None, appointments=[APPT], instantly=None, do_proposals=True)
        results.append(result)
        return result

    runs, pushes = _window_runs(store, run)
    assert runs == 140
    assert all(r["proposals"] == [{"id": "appt-1", "skipped": "no_show"}] for r in results)
    assert pushes == 1, "a skipped row pushes once per call, not on every run"


def test_the_same_error_pushes_about_once_an_hour(tmp_env):
    store = JsonFileStore(tmp_env / "precall_store.json")
    error = {"where": "proposal", "id": "appt-1", "error": "GHL 502 Bad Gateway"}

    def run(t):
        return {"briefs": [], "proposals": [], "errors": [dict(error)]}

    runs, pushes = _window_runs(store, run)
    hours = len(set((START + timedelta(minutes=20 + 5 * i)).strftime("%H") for i in range(runs)))
    assert pushes == hours, (pushes, hours)          # one per clock hour the error persists
    assert pushes <= runs // 10


def test_a_new_error_pushes_at_once_even_inside_the_same_hour(tmp_env):
    store = JsonFileStore(tmp_env / "precall_store.json")
    t = START + timedelta(minutes=25)
    first = {"briefs": [], "proposals": [], "errors": [{"where": "brief", "id": "a", "error": "boom"}]}
    second = {"briefs": [], "proposals": [], "errors": [{"where": "brief", "id": "b", "error": "other"}]}
    assert pt.scheduled_push_due(first, False, store, t) is True
    assert pt.scheduled_push_due(first, False, store, t + timedelta(minutes=5)) is False
    assert pt.scheduled_push_due(second, False, store, t + timedelta(minutes=10)) is True


def test_briefs_and_drafted_proposals_always_push_and_idle_runs_never(tmp_env):
    store = JsonFileStore(tmp_env / "precall_store.json")
    t = START
    assert pt.scheduled_push_due({"briefs": [{"id": "a"}], "proposals": [], "errors": []}, False, store, t)
    assert pt.scheduled_push_due({"briefs": [], "proposals": [{"id": "p", "company": "X"}], "errors": []},
                                 False, store, t)
    assert pt.scheduled_push_due({"briefs": [{"id": "a"}], "proposals": [], "errors": []}, False, store, t)
    assert not pt.scheduled_push_due({"briefs": [], "proposals": [], "errors": []}, False, store, t)
