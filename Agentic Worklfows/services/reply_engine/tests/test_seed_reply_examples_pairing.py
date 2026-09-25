"""The seed pairs his reply only with a message the lead sent (2026-09-25).

jobs/seed_reply_examples.find_examples walks a thread oldest first. Only a
lead's row (ue_type 2, or no ue_type and not outbound) is "the lead's
message"; a campaign step (ue_type 1) or scheduled send (ue_type 4) of ours
clears it, so our own email is never recorded as what he answered.

Pure: no store, no network, every lead fictional.
"""
from datetime import datetime, timedelta, timezone

from jobs import seed_reply_examples as seed
from services.reply_engine import cadence

INBOX = "lorenzo@advero-mail.example"
LEAD = "jordan@leadco.example"
THREAD = "thread-pairing-1"
START = datetime(2026, 9, 15, tzinfo=timezone.utc)
T0 = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
INDEX = {"labels": {}, "engine_ids": set(), "engine_times": {}, "thread_leads": {}}


def _row(eid, minutes, ue_type=None, from_lead=False):
    row = {"id": eid, "thread_id": THREAD, "eaccount": INBOX,
           "timestamp_created": (T0 + timedelta(minutes=minutes)).isoformat(),
           "from_address_email": LEAD if from_lead else INBOX,
           "to_address_email_list": INBOX if from_lead else LEAD,
           "subject": "Re: quick question"}
    if ue_type is not None:
        row["ue_type"] = ue_type
    return row


def _lead(eid, minutes, ue_type=2):
    return _row(eid, minutes, ue_type=ue_type, from_lead=True)


def _his(eid, minutes, ue_type=3):
    return _row(eid, minutes, ue_type=ue_type)


def _find(rows):
    return seed.find_examples(rows, START, INDEX)


def _skipped(found, eid):
    return [s["reason"] for s in found["skipped"] if s["email_id"] == eid]


def test_a_campaign_step_after_the_lead_message_clears_it():
    found = _find([_lead("in-1", 0), _row("step-1", 10, ue_type=1), _his("out-1", 20)])
    assert found["examples"] == [] and _skipped(found, "out-1") == ["no_lead_message"]


def test_a_scheduled_send_after_the_lead_message_clears_it():
    found = _find([_lead("in-1", 0), _row("sched-1", 10, ue_type=4), _his("out-1", 20)])
    assert found["examples"] == [] and _skipped(found, "out-1") == ["no_lead_message"]


def test_a_campaign_step_is_never_paired_as_the_lead_message():
    found = _find([_row("step-1", 0, ue_type=1), _his("out-1", 20)])
    assert found["examples"] == [] and _skipped(found, "out-1") == ["no_lead_message"]


def test_a_lead_row_then_his_reply_is_paired():
    found = _find([_row("step-1", 0, ue_type=1), _lead("in-1", 10), _his("out-1", 20)])
    assert [(e["email_id"], e["lead_message_id"]) for e in found["examples"]] == [("out-1", "in-1")]
    assert found["examples"][0]["lead_email"] == LEAD


def test_a_lead_row_without_ue_type_is_paired():
    found = _find([_lead("in-1", 0, ue_type=None), _his("out-1", 20, ue_type=None)])
    assert [(e["email_id"], e["lead_message_id"]) for e in found["examples"]] == [("out-1", "in-1")]


def test_a_row_of_ours_without_ue_type_that_is_not_his_hand_send_clears_it(monkeypatch):
    # Only the row "auto-1" (outbound from our inbox, no ue_type) is taken as
    # not sent by hand; the lead's message before it must not survive it.
    real = cadence._sent_by_hand
    monkeypatch.setattr(cadence, "_sent_by_hand", lambda row: False if row.get("id") == "auto-1" else real(row))
    found = _find([_lead("in-1", 0, ue_type=None), _row("auto-1", 10), _his("out-1", 20, ue_type=None)])
    assert found["examples"] == [] and _skipped(found, "out-1") == ["no_lead_message"]


def test_the_leads_auto_reply_still_leaves_the_message_pending():
    auto = dict(_lead("in-2", 10), subject="Automatic reply: out of office")
    found = _find([_lead("in-1", 0), auto, _his("out-1", 20)])
    assert [(e["email_id"], e["lead_message_id"]) for e in found["examples"]] == [("out-1", "in-1")]
