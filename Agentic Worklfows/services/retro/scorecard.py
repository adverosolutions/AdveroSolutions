"""The weekly client scorecard (Blueprint F3, brief A12), from the same week.

A12 does not need its own generator. Collect the week once with
``collect.collect_week``, then:

    from services.retro import collect, scorecard, render
    card = scorecard.build_client_scorecard(
        week, client_name="Shining Armor Cleaning",
        campaign_keys=["cleaning_reactivation"],
        wins=[...], next_steps=[...], open_questions=[...])
    markdown = scorecard.render_client_scorecard(card)   # copy-checked

``render_client_scorecard`` runs the offer-sheet copy rules over the finished
markdown and raises ``render.ClientCopyError`` rather than handing back a
document that says "automation" or carries an em dash. For performance deals
this scorecard is the invoice basis, so the numbers in it are the same numbers
the internal packet prints, filtered to the client's campaigns. Nothing is
rounded up in the client's favour and nothing missing is shown as a zero: a
metric with no source is left out and named in the closing note.
"""
from typing import Any, Dict, List, Optional

from shared import settings

from . import metrics as metrics_mod
from . import render
from .render import Packet, Section, fmt_number

CLIENT_METRIC_ORDER = (
    "sent", "real_replies", "real_reply_rate",
    "positives", "booked", "held", "closes", "revenue",
)


class UnknownCampaign(ValueError):
    """A campaign key that is not in config/ids.json."""


def _campaign_ids(campaign_keys):
    # type: (Optional[List[str]]) -> Optional[List[str]]
    """Instantly campaign ids for these keys, or a raised error.

    A key that is not in ``settings.CAMPAIGNS`` used to be skipped silently, so
    ``--campaigns cleaning`` (the real key is ``cleaning_reactivation``)
    rendered a perfectly valid client scorecard reading "Interested 0, Calls
    booked 0, Calls held 0, Signed 0" and sent a report of a total failure week
    to a client. A typo is not a zero.
    """
    if not campaign_keys:
        return None
    known = settings.CAMPAIGNS or {}
    unknown = [k for k in campaign_keys if not (known.get(k) or {}).get("id")]
    if unknown:
        raise UnknownCampaign(
            "unknown campaign key(s): %s. The keys in config/ids.json are: %s"
            % (", ".join(sorted(unknown)), ", ".join(sorted(known)) or "(none configured)"))
    return [known[k]["id"] for k in campaign_keys]


def client_caveats(week):
    # type: (Any) -> List[str]
    """What a client has to know, in words a client can read.

    The internal packet carries these already; the scorecard used to carry
    none, and it is the invoice basis for a performance deal. The live case is
    on file: a lead with a call booked and held in GHL is still
    ``lt_interest_status: 1`` in Instantly because the mirror job is not live,
    so the card read "Calls booked 0, Calls held 0, Signed 0" for a week whose
    call the client attended. Either that under-bills Lorenzo or it gets
    disputed by somebody who was on the call.

    Offer-sheet copy rules apply, so no internal vocabulary and no jargon:
    ``render.require_client_copy`` runs over the finished document.
    """
    out = []
    if week.this_window.partial_last_day:
        out.append(
            "This week is counted through %s CT on %s, so the last day is not complete yet."
            % (week.now.strftime("%H:%M"), week.this_window.end_date))
    booked = None
    for metric in week.funnel:
        if metric.key == "booked":
            booked = metric
            break
    if booked is not None and "Instantly" in (booked.source or ""):
        out.append(
            "Calls booked, calls held and signed deals are read from the sending platform, which "
            "only shows them once the reply is marked by hand. Treat those three rows as a floor "
            "and check them against your own calendar; anything you know happened that is not "
            "here, tell Lorenzo and he will correct it before invoicing.")
    for source_name in ("accounts_daily", "campaigns_daily", "leads"):
        source = week.sources.get(source_name)
        if source is not None and not source.ok:
            out.append(
                "Some figures could not be read from the sending platform for this period, so "
                "they are left out below rather than shown as a zero.")
            break
    return out


def _filter_leads(leads, campaign_ids):
    # type: (List[Dict[str, Any]], Optional[List[str]]) -> List[Dict[str, Any]]
    if campaign_ids is None:
        return list(leads or [])
    allowed = set(campaign_ids)
    return [l for l in (leads or [])
            if (l.get("campaign") or l.get("campaign_id")) in allowed]


def client_funnel(week, campaign_keys=None, attributed_revenue=None):
    # type: (Any, Optional[List[str]], Optional[float]) -> List[metrics_mod.Metric]
    """The client's slice of the week, as Metric objects.

    Sends and replies come from the per-campaign daily rows (so a client who
    owns two of the six campaigns sees only those two); positives and onward
    come from the leads in those campaigns.
    """
    keys = campaign_keys or list((week.per_campaign.get("this") or {}).keys())
    campaign_ids = _campaign_ids(campaign_keys)
    daily_src = (getattr(week, "sources", None) or {}).get("campaigns_daily")
    daily_ok = daily_src is None or daily_src.ok

    def totals(bucket):
        """The client's campaigns summed, or None when any of them could not
        be read. A partial sum is a number that looks measured and is short,
        and a summed zero from a failed read printed "Emails sent 0" directly
        above the caveat that says such figures are left out."""
        per = week.per_campaign.get(bucket) or {}
        if not keys or (not daily_ok and not per):
            return None
        merged = {}  # type: Dict[str, float]
        for key in keys:
            if key not in per or per.get(key) is None:
                return None
            for field, value in per[key].items():
                merged[field] = merged.get(field, 0.0) + value
        return merged

    this_totals = totals("this")
    last_totals = totals("last")
    # Filter to the client's campaigns first, then one record per email: the
    # same person on two of the client's campaigns is one interested contact.
    leads, _collapsed = metrics_mod.dedupe_by_email(
        _filter_leads(getattr(week, "leads", []), campaign_ids))
    leads_src = (getattr(week, "sources", None) or {}).get("leads")
    leads_ok = leads_src is None or leads_src.ok
    this_status = metrics_mod.count_statuses(leads, week.this_window) if leads_ok else {}
    last_status = metrics_mod.count_statuses(leads, week.last_window) if leads_ok else {}

    this_sent = this_totals.get("sent") if this_totals is not None else None
    last_sent = last_totals.get("sent") if last_totals is not None else None
    this_real = metrics_mod.real_replies(this_totals) if this_totals else None
    last_real = metrics_mod.real_replies(last_totals) if last_totals else None

    unread = "could not be read from the sending platform this week"
    send_note = unread if this_totals is None else ""
    status_note = unread if not leads_ok else ""
    out = [
        metrics_mod.Metric("sent", "Emails sent", this_sent, last_sent, "", "Instantly",
                           note=send_note),
        metrics_mod.Metric("real_replies", "Replies from a person", this_real, last_real,
                           "", "Instantly", note=send_note),
        metrics_mod.Metric("real_reply_rate", "Reply rate",
                           (this_real / this_sent) if (this_real is not None and this_sent) else None,
                           (last_real / last_sent) if (last_real is not None and last_sent) else None,
                           "%", "Instantly", note=send_note),
        metrics_mod.Metric("positives", "Interested", this_status.get("positives"),
                           last_status.get("positives"), "", "Instantly", note=status_note),
        metrics_mod.Metric("booked", "Calls booked", this_status.get("booked"),
                           last_status.get("booked"), "", "Instantly", note=status_note),
        metrics_mod.Metric("held", "Calls held", this_status.get("held"),
                           last_status.get("held"), "", "Instantly", note=status_note),
        metrics_mod.Metric("closes", "Signed", this_status.get("closes"),
                           last_status.get("closes"), "", "Instantly", note=status_note),
    ]
    if attributed_revenue is not None:
        out.append(metrics_mod.Metric("revenue", "Revenue attributed", attributed_revenue,
                                      None, "$", "agreed attribution"))
    else:
        out.append(metrics_mod.Metric(
            "revenue", "Revenue attributed", None, None, "$", "",
            note="pending the signed-contract values for this period"))
    return out


def build_client_scorecard(week, client_name, campaign_keys=None, wins=None, next_steps=None,
                           open_questions=None, attributed_revenue=None, plan=None):
    # type: (Any, str, Optional[List[str]], Optional[List[str]], Optional[List[str]], Optional[List[str]], Optional[float], Optional[List[str]]) -> Packet
    """Nick's agenda shape: the numbers, then wins, next steps, open questions."""
    funnel = client_funnel(week, campaign_keys, attributed_revenue)
    reported = [m for m in funnel if m.available]
    missing = [m for m in funnel if not m.available]

    sections = [
        Section(
            "Where the week landed",
            body="%s." % week.this_window.describe(),
            table=render.metric_table(reported, this_label="This week", last_label="Last week",
                                      include_source=False),
            note=("Not reported this week: %s." % ", ".join(
                "%s (%s)" % (m.label, m.note or "no source") for m in missing)) if missing else None,
        ),
        Section("Wins", bullets=list(wins or []) or ["Nothing to report this week."]),
        Section("Next steps", bullets=list(next_steps or []) or ["Nothing outstanding."]),
        Section("Open questions", bullets=list(open_questions or []) or ["None."]),
        Section("The plan for next week", bullets=list(plan or []) or
                ["Keep the sequences running and report again on Friday."]),
    ]
    # Signature last among the sections; render_markdown then appends the
    # "How to read these numbers" block underneath it, which is where notes on
    # a report belong.
    sections.append(Section("", body="Lorenzo"))
    return Packet(
        title="%s, week of %s" % (client_name, week.this_window.start_date),
        subtitle="Prepared %s." % week.now.strftime("%Y-%m-%d"),
        sections=sections,
        caveats=client_caveats(week),
        caveats_heading="How to read these numbers",
        meta={"client": client_name, "week": week.this_window.start_date,
              "campaigns": list(campaign_keys or [])},
    )


def render_client_scorecard(packet):
    # type: (Packet) -> str
    """Render and enforce the copy rules. Raises render.ClientCopyError."""
    markdown = render.render_markdown(packet)
    return render.require_client_copy(markdown)


def scorecard_numbers(week, campaign_keys=None):
    # type: (Any, Optional[List[str]]) -> Dict[str, Any]
    """The same numbers as a dict, for an invoice line or a GHL note."""
    return dict(
        (m.key, {"value": m.this_week, "label": m.label,
                 "formatted": fmt_number(m.this_week, m.unit)})
        for m in client_funnel(week, campaign_keys)
    )
