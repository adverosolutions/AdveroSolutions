#!/usr/bin/env python3
"""Build ORG_STRUCTURE.excalidraw (v3) and ORG_STRUCTURE.png (if matplotlib is available).

Rerun: ~/.venvs/plot/bin/python ~/advero/state/org/build_org_excalidraw.py   (JSON + PNG)
       python3 ~/advero/state/org/build_org_excalidraw.py                    (JSON only)
Content source of truth: ORG_STRUCTURE.md v3, APPROVED 2026-10-21 (same folder); option 2 LinkedIn (li-227). v1 and v2 kept as *.bak-20261021-v1 / -v2.
"""
import json, os, random, sys, textwrap, time

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(OUT_DIR, "ORG_STRUCTURE.excalidraw")
OUT_PNG = os.path.join(OUT_DIR, "ORG_STRUCTURE.png")

rng = random.Random(20261021)
NOW = int(time.time() * 1000)
FONT, FS = 2, 16

STYLES = {
    "owner":    dict(stroke="#e67700", bg="#fff3bf", dash="solid"),
    "ops":      dict(stroke="#6741d9", bg="#e5dbff", dash="solid"),
    "existing": dict(stroke="#1971c2", bg="#d0ebff", dash="solid"),
    "manager":  dict(stroke="#2f9e44", bg="#d3f9d8", dash="solid"),
    "newhire":  dict(stroke="#e8590c", bg="#ffe8cc", dash="dashed"),
    "park":     dict(stroke="#c92a2a", bg="#fff5f5", dash="dashed"),
    "worker":   dict(stroke="#0c8599", bg="#e3fafc", dash="solid"),
    "pending":  dict(stroke="#e8590c", bg="#fff9db", dash="dotted"),
    "planned":  dict(stroke="#868e96", bg="#f1f3f5", dash="dashed"),
    "duty":     dict(stroke="#868e96", bg="#ffffff", dash="dotted"),
    "header":   dict(stroke="#343a40", bg="#e9ecef", dash="solid"),
}
ROOM_COLOR = "#5f3dc4"

elements, by_id, frames = [], {}, []


def base(eid, etype, x, y, w, h, stroke, bg, dash="solid", sw=2, roundness=None, frame=None):
    e = {"id": eid, "type": etype, "x": x, "y": y, "width": w, "height": h, "angle": 0,
         "strokeColor": stroke, "backgroundColor": bg, "fillStyle": "solid", "strokeWidth": sw,
         "strokeStyle": dash, "roughness": 0, "opacity": 100, "groupIds": [], "frameId": frame,
         "roundness": roundness, "seed": rng.randint(1, 2**31 - 1), "version": 1,
         "versionNonce": rng.randint(1, 2**31 - 1), "isDeleted": False, "boundElements": [],
         "updated": NOW, "link": None, "locked": False}
    elements.append(e); by_id[eid] = e
    return e


def wrap(text, w, fs):
    chars = max(8, int((w - 20) / (fs * 0.55)))
    out = []
    for para in text.split("\n"):
        out.extend(textwrap.wrap(para, chars) or [""])
    return out


def box(eid, x, y, w, h, label, style, fs=FS, frame=None):
    st = STYLES[style]
    r = base(eid, "rectangle", x, y, w, h, st["stroke"], st["bg"], st["dash"], roundness={"type": 3}, frame=frame)
    lines = wrap(label, w, fs)
    th = len(lines) * fs * 1.25
    tw = min(w - 10, max(len(l) for l in lines) * fs * 0.55)
    t = base(eid + "_t", "text", x + (w - tw) / 2, y + (h - th) / 2, tw, th, "#1e1e1e", "transparent", sw=1, frame=frame)
    t.update({"text": "\n".join(lines), "fontSize": fs, "fontFamily": FONT, "textAlign": "center",
              "verticalAlign": "middle", "baseline": int(fs * 0.9), "containerId": eid,
              "originalText": label, "lineHeight": 1.25, "autoResize": True})
    r["boundElements"].append({"id": t["id"], "type": "text"})
    return r


def free_text(eid, x, y, text, fs=FS, color="#1e1e1e"):
    lines = text.split("\n")
    w, h = max(len(l) for l in lines) * fs * 0.55, len(lines) * fs * 1.25
    t = base(eid, "text", x, y, w, h, color, "transparent", sw=1)
    t.update({"text": text, "fontSize": fs, "fontFamily": FONT, "textAlign": "left", "verticalAlign": "top",
              "baseline": int(fs * 0.9), "containerId": None, "originalText": text, "lineHeight": 1.25,
              "autoResize": True})
    return t


def arrow(eid, src, dst, pts_abs, dash="solid", color="#495057", frame=None):
    x0, y0 = pts_abs[0]
    pts = [[px - x0, py - y0] for px, py in pts_abs]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    a = base(eid, "arrow", x0, y0, max(xs) - min(xs), max(ys) - min(ys), color, "transparent", dash, frame=frame)
    a.update({"points": pts, "lastCommittedPoint": None,
              "startBinding": {"elementId": src, "focus": 0, "gap": 1},
              "endBinding": {"elementId": dst, "focus": 0, "gap": 1},
              "startArrowhead": None, "endArrowhead": "arrow", "elbowed": False})
    by_id[src]["boundElements"].append({"id": eid, "type": "arrow"})
    by_id[dst]["boundElements"].append({"id": eid, "type": "arrow"})
    return a


def room(fid, name, x, y, w, h):
    """Branch team chat room as an Excalidraw frame (members get frameId)."""
    frames.append(dict(id=fid, name=name, x=x, y=y, w=w, h=h))


# ---------------- layout
X0, GAP, COLW = 40, 70, 260
BUS_Y, HDR_Y, HDR_H, MGR_Y, MGR_H = 340, 380, 50, 500, 110
ROW0, STEP, CH = 660, 135, 105
FPAD = 14

# key, header, width, room name or None, manager (label, style), children [(id, label, style, arrow dash)]
columns = [
    ("upwork", "UPWORK", 600, "Upwork team room", ("Upwork Coordinator\nBranch Manager\nScoring, MCP client cross-check, pick flow, rooms", "manager"), None),
    ("cold", "COLD EMAIL", COLW, "Cold Email team room", ("Cold Email Manager\nNEW BOT\nReply intake, handoffs, daily pipeline review", "newhire"),
        [("deliv", "Deliverability Specialist\n60 inboxes, 30 domains", "existing", "solid"),
         ("appt", "Appointment Setter\nTimes offered to held call; takes LinkedIn bookings", "existing", "solid"),
         ("copy", "Copywriter\nPARKED (on-call)", "park", "dashed"),
         ("sender", "Sender (duty, no bot)\nInstantly: campaigns\nCOO: approved replies\nAppt Setter: bookings", "duty", "dotted")]),
    ("leadgen", "LEAD GEN", COLW, "Lead Gen team room", ("Lead Gen Manager\nPROMOTED (was Lead Gen Specialist)\nSummary to COO 7:15 AM", "manager"),
        [("qe", "QuickEnrich bot\nNEW\nbrowser only; MV existing credits", "newhire", "solid"),
         ("maps", "Maps bot\nNEW\nfree crawler, 10 metros/night", "newhire", "solid"),
         ("vollna", "Vollna bot\nNEW\nRSS + Load more sweeps; file to Upwork", "newhire", "solid"),
         ("salesnav", "Sales Nav bot\nNEW, named LinkedIn bot (li-227)\nholds gate 6:00 to 6:40 AM", "newhire", "solid")]),
    ("linkedin", "LINKEDIN", COLW, "LinkedIn team room", ("LinkedIn Outreach Manager\nBranch Manager, delegator\nNamed LinkedIn bot, no prospecting", "manager"),
        [("setter", "LinkedIn Setter / SDR\nNEW, named LinkedIn bot (li-227)\nlist, accepts, read + draft convos", "newhire", "solid"),
         ("licontent", "LinkedIn Content Manager\nweekly; PARK Oct 26 if blocked", "park", "dashed"),
         ("ligate", "linkedin_gate (lock, not a bot)\nOne LinkedIn session at a time\nOutreach Mgr, Setter, Sales Nav\n(li-227)", "duty", "dotted")]),
    ("community", "COMMUNITY", COLW, "Community team room", ("Community Manager\nBranch Manager\nJoins, calendar, approvals via COO", "manager"),
        [("cengage", "Community Engagement bot\nNEW\nscans, comment drafts, tracker", "newhire", "solid"),
         ("ccontent", "Community Content bot\nNEW\nposts, daily accountability draft", "newhire", "solid"),
         ("coutreach", "Community Outreach bot\nPLANNED (5+ DM-permission convos/week)", "planned", "dashed")]),
    ("finance", "FINANCE (via COO, no room)", COLW, None, ("Accounting\nCross-branch, reports via COO\nweekly spend, Connects, cash", "existing"), []),
    ("ops", "REVENUE OPS (via COO, no room)", COLW, None, ("Revenue Operations\nCross-branch QA, reports via COO\nCRM, stalled flag, sprint row", "existing"), []),
]

total_w = sum(c[2] for c in columns) + GAP * (len(columns) - 1)
mid = X0 + total_w / 2

box("lorenzo", mid - 170, 60, 340, 90, "Lorenzo\nOwner / CEO\nTalks only to COO", "owner", fs=18)
box("coo", mid - 190, 200, 380, 95, "COO / Chief of Staff\nTalks only to branch managers\nIn no team room", "ops", fs=17)
arrow("a_lorenzo_coo", "lorenzo", "coo", [(mid, 151), (mid, 199)])

x = X0
for key, header, w, rname, (mlabel, mstyle), children in columns:
    fid = "room_" + key if rname else None
    box("hdr_" + key, x, HDR_Y, w, HDR_H, header, "header", fs=18)
    mgr = "mgr_" + key
    box(mgr, x, MGR_Y, w, MGR_H, mlabel, mstyle, frame=fid)
    lane = x - 32
    arrow("a_coo_" + key, "coo", mgr,
          [(mid, 296), (mid, BUS_Y), (lane, BUS_Y), (lane, MGR_Y + MGR_H / 2), (x - 1, MGR_Y + MGR_H / 2)])
    bottom = MGR_Y + MGR_H
    mb = MGR_Y + MGR_H
    if key == "upwork":
        box("demo", x + 40, ROW0, w - 40, CH,
            "Demo Builder\n+ Demo Build Manager duty (lead builder, sole final review U-014)\nAssigns each approved job to one worker", "existing", frame=fid)
        arrow("a_up_demo", mgr, "demo", [(x + 20, mb + 1), (x + 20, ROW0 + CH / 2), (x + 39, ROW0 + CH / 2)], frame=fid)
        wy, ww, wg = ROW0 + STEP + 10, 128, 16
        workers = [("w1", "Builder worker 1\nsubagent", "worker", "solid"), ("w2", "Builder worker 2\nsubagent", "worker", "solid"),
                   ("w3", "Builder worker 3\nsubagent", "worker", "solid"), ("w45", "Workers 4-5\nPLANNED (over 15/day)", "planned", "dashed")]
        for i, (wid, wl, ws, wd) in enumerate(workers):
            wx = x + 40 + i * (ww + wg)
            box(wid, wx, wy, ww, CH, wl, ws, fs=15, frame=fid)
            arrow("a_demo_" + wid, "demo", wid, [(wx + ww / 2, ROW0 + CH + 1), (wx + ww / 2, wy - 1)], dash=wd,
                  color="#868e96" if wd == "dashed" else "#495057", frame=fid)
        ky = wy + STEP
        box("kb", x + 40, ky, w - 40, CH,
            "Shared KB, single source (read-only for workers)\nMac: upwork-pipeline/ DIRECTIVES, UPWORK_PROCESS, templates, brand.css\nBox mirror: /workspace/upwork-onboarding/\nClaim lock: dbq.py queue.json, one job per worker", "duty", fs=14, frame=fid)
        bottom = ky + CH
    else:
        for i, (cid, cl, cs, cd) in enumerate(children):
            cy = ROW0 + i * STEP
            h = CH + (35 if cs == "duty" else 0)
            box(cid, x + 40, cy, w - 40, h, cl, cs, frame=fid)
            arrow("a_%s_%s" % (key, cid), mgr, cid, [(x + 20, mb + 1), (x + 20, cy + h / 2), (x + 39, cy + h / 2)],
                  dash=cd, color="#495057" if cd == "solid" else "#868e96", frame=fid)
            bottom = cy + h
    if rname:
        room(fid, rname, x - FPAD, MGR_Y - FPAD - 6, w + 2 * FPAD, bottom - MGR_Y + 2 * FPAD + 6)
    x += w + GAP

# legend (top left)
free_text("legend_title", X0, 30, "Legend", fs=18)
legend = [("lg_existing", "Existing bot, keep", "existing"), ("lg_manager", "Branch manager (existing bot)", "manager"),
          ("lg_newhire", "NEW bot (created 2026-10-21)", "newhire"), ("lg_park", "PARKED or park date set", "park"),
          ("lg_worker", "Builder worker (subagent, shared KB)", "worker"), ("lg_planned", "Planned, later", "planned"),
          ("lg_duty", "Duty or file, not a bot", "duty")]
for i, (lid, lt, ls_) in enumerate(legend):
    box(lid, X0, 58 + i * 34, 330, 28, lt, ls_, fs=13)
room("room_legend", "Team chat room (branch only)", X0 + 350, 72, 190, 60)
free_text("legend_room_note", X0 + 350, 140, "Frame = branch room.\nCOO not in rooms.\nNo cross-branch or\nall-bots room.\nNo posts 9 PM to 6 AM.", fs=13)

free_text("title", X0 + total_w - 700, 30,
          "AdveroSolutions org structure v3 APPROVED 2026-10-21 (20 bots)\n"
          "Arrows = reporting lines only: Lorenzo > COO > manager > bot.\n"
          "Cross-branch work goes manager > COO > manager.\n"
          "Rooms coordinate; decisions escalate up the chain.\n"
          "Managers send one summary to COO; COO rolls up to Lorenzo 9:15 AM.\n"
          "LinkedIn: 3 named bots, one session at a time via the gate (li-227).\n"
          "Goal tracked: $20K 90 Day Sprint ($25K stretch: Lorenzo to confirm).", fs=15)

# frames go after their children (Excalidraw convention)
for f in frames:
    e = base(f["id"], "frame", f["x"], f["y"], f["w"], f["h"], "#bbb", "transparent", "solid", sw=2)
    e["name"] = f["name"]

doc = {"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": elements,
       "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None}, "files": {}}

# ---------------- verification
def inter(a, b):
    return a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"] and \
           a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"]

def inside(a, f):
    return a["x"] >= f["x"] and a["y"] >= f["y"] and a["x"] + a["width"] <= f["x"] + f["width"] and \
           a["y"] + a["height"] <= f["y"] + f["height"]

rs = [e for e in elements if e["type"] == "rectangle"]
fs_ = [e for e in elements if e["type"] == "frame"]
problems = []
problems += [("rect overlap", a["id"], b["id"]) for i, a in enumerate(rs) for b in rs[i + 1:] if inter(a, b)]
problems += [("frame overlap", a["id"], b["id"]) for i, a in enumerate(fs_) for b in fs_[i + 1:] if inter(a, b)]
for f in fs_:
    for r in rs:
        if r["frameId"] == f["id"] and not inside(r, f):
            problems.append(("member outside its room", r["id"], f["id"]))
        if r["frameId"] != f["id"] and inter(r, f):
            problems.append(("non-member inside room", r["id"], f["id"]))
    # frame name label sits about 24px above the frame
    lab = {"x": f["x"], "y": f["y"] - 26, "width": len(f["name"]) * 8, "height": 22}
    problems += [("room label overlap", f["id"], r["id"]) for r in rs if inter(lab, r)]
for t in [e for e in elements if e["type"] == "text" and e["containerId"] is None]:
    problems += [("free text overlap", t["id"], o["id"]) for o in rs + fs_ if inter(t, o)]
problems += [("text overflow", t["id"], t["containerId"]) for t in elements if t["type"] == "text" and t["containerId"]
             and (t["width"] > by_id[t["containerId"]]["width"] or t["height"] > by_id[t["containerId"]]["height"])]
for a in [e for e in elements if e["type"] == "arrow"]:
    for k in ("startBinding", "endBinding"):
        tgt = by_id.get(a[k]["elementId"])
        if not tgt or tgt["type"] != "rectangle" or not any(be["id"] == a["id"] for be in tgt["boundElements"]):
            problems.append(("binding", a["id"], k))
ids = [e["id"] for e in elements]
if len(ids) != len(set(ids)):
    problems.append(("duplicate ids", "", ""))
REQ = ["id", "type", "x", "y", "width", "height", "angle", "strokeColor", "backgroundColor", "fillStyle", "strokeWidth",
       "strokeStyle", "roughness", "opacity", "groupIds", "roundness", "seed", "version", "versionNonce", "isDeleted",
       "boundElements", "updated", "link", "locked"]
for e in elements:
    miss = [k for k in REQ if k not in e]
    if e["type"] == "text":
        miss += [k for k in ["text", "fontSize", "fontFamily", "textAlign", "verticalAlign", "originalText", "lineHeight", "containerId"] if k not in e]
    if e["type"] == "arrow":
        miss += [k for k in ["points", "startBinding", "endBinding", "startArrowhead", "endArrowhead"] if k not in e]
    if miss:
        problems.append(("missing fields", e["id"], miss))

s = json.dumps(doc, indent=2)
with open(OUT_JSON, "w") as f:
    f.write(s)
json.load(open(OUT_JSON))
print("elements:", len(elements), "| rectangles:", len(rs), "| arrows:", sum(e["type"] == "arrow" for e in elements),
      "| rooms (frames):", len(fs_))
print("JSON valid: yes")
print("checks:", problems or "all passed (no rect/frame overlaps, members inside rooms, text fits, bindings ok, fields ok)")
if problems:
    sys.exit(1)

# ---------------- PNG preview
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle
except ImportError:
    print("PNG: skipped (no matplotlib)")
    sys.exit(0)

minx = min(e["x"] for e in elements) - 30; maxx = max(e["x"] + e["width"] for e in elements) + 30
miny = min(e["y"] for e in elements) - 40; maxy = max(e["y"] + e["height"] for e in elements) + 30
fig = plt.figure(figsize=((maxx - minx) / 100.0, (maxy - miny) / 100.0), dpi=110)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(minx, maxx); ax.set_ylim(maxy, miny); ax.axis("off")
LS = {"solid": "-", "dashed": (0, (6, 4)), "dotted": (0, (1.5, 3))}
esc = lambda t: t.replace("$", r"\$")
for e in fs_:
    ax.add_patch(Rectangle((e["x"], e["y"]), e["width"], e["height"], fc="#f8f0fc", ec=ROOM_COLOR, lw=1.6,
                           linestyle=(0, (8, 5)), zorder=0))
    ax.text(e["x"] + 4, e["y"] - 6, e["name"], ha="left", va="bottom", fontsize=11, color=ROOM_COLOR, zorder=4)
for e in elements:
    if e["type"] == "arrow":
        P = [(e["x"] + p[0], e["y"] + p[1]) for p in e["points"]]
        ax.plot([p[0] for p in P], [p[1] for p in P], color=e["strokeColor"], lw=1.4, linestyle=LS[e["strokeStyle"]], zorder=1)
        ax.annotate("", xy=P[-1], xytext=P[-2], arrowprops=dict(arrowstyle="-|>", color=e["strokeColor"], lw=1.4), zorder=2)
for e in rs:
    ax.add_patch(FancyBboxPatch((e["x"], e["y"]), e["width"], e["height"], boxstyle="round,pad=0,rounding_size=8",
                 fc=e["backgroundColor"], ec=e["strokeColor"], lw=1.8, linestyle=LS[e["strokeStyle"]], zorder=3))
for e in elements:
    if e["type"] == "text":
        pts = e["fontSize"] * 0.72
        if e["containerId"]:
            c = by_id[e["containerId"]]
            ax.text(c["x"] + c["width"] / 2, c["y"] + c["height"] / 2, esc(e["text"]), ha="center", va="center",
                    fontsize=pts, zorder=4, linespacing=1.2)
        else:
            ax.text(e["x"], e["y"], esc(e["text"]), ha="left", va="top", fontsize=pts, zorder=4, linespacing=1.2)
fig.savefig(OUT_PNG, facecolor="white")
print("PNG:", OUT_PNG)
