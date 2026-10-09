"""Build the HighLevel portfolio deck PDF.

1. Crops / resizes the final screenshots into deck/assets/ (PIL). The workflow crops are found
   from the screenshot content (header row, node column, canvas edges), so sharper or re-zoomed
   captures can replace the files in final/ without touching this script. The crop sizes drive
   the slide layout, which is written to deck/assets/layout.css.
2. Bakes every slide's visual layer (background, panels, frames, shadows, screenshots) at 2x into
   one 3840x2160 JPEG per slide with Playwright (Chrome), text hidden.
3. Prints deck.html in "baked" mode to final/home-service-lead-system.pdf: one JPEG per page with
   the titles, captions and page numbers on top as real text. The PDF carries no CSS blur shadows
   and no soft masks (Apple's PDF engine draws Chrome's shadow soft masks as solid gray boxes).
4. Rasterises every PDF page with pdf.js into deck/.check/slide-NN.png and with Apple's engine
   (CoreGraphics, plus Quick Look on single-page splits) into deck/.check/apple-*.png, then
   compares the two renders page by page.

Run: python3 build_deck.py
"""
import base64
import io
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FINAL = HERE.parent / "final"
ASSETS = HERE / "assets"
CHECK = HERE / ".check"
PDF_OUT = FINAL / "home-service-lead-system.pdf"
LAYOUT_CSS = ASSETS / "layout.css"
ASSET_QUALITY = 95   # intermediate assets; they are re-encoded once more in the slide bake
BAKE_QUALITY = 90    # the per-slide JPEG that ends up in the PDF
MIN_DENSITY = 1.5    # embedded pixels per displayed CSS px
TARGET_DENSITY = 1.7  # downscale target when the source is much denser
MAX_PDF_MB = 15

# Slide geometry shared with deck.html.
SLIDE_W, SLIDE_H = 1920, 1080
SIDE = 88                      # left/right page margin
TEXT_RIGHT = SIDE + 500        # right edge of the .text column on workflow slides
V_MARGIN = 88                  # top/bottom margin for the workflow panels
CHROME = 22                    # .panel padding (10) + border (1), both sides
WF_IMG_H = SLIDE_H - 2 * V_MARGIN - CHROME   # 882: screenshot height inside a workflow panel
MIN_GAP = 100                  # minimum gap between the text column and a workflow panel
END_CLEAR = 15                 # display px of clear canvas kept under END
CARD_CLEAR = 6                 # display px of clear canvas kept between a panel edge and a node/"+"
ARROW_GAP = 104                # minimum gap between the two Quote Follow-Up panels (arrow is 52)

# name -> (source file, crop box in source px or None, displayed CSS width in deck.html)
STATIC_SPECS = {
    # Pipeline is a 1x capture; the sidebar (agency logo, account switcher) is cropped off.
    "pipeline": ("pipeline-board.png", (223, 0, 1488, 784), 1180),
    # Funnel: first ~890 CSS px of desktop (hero + form), first 844 CSS px of mobile.
    "quote-desktop": ("funnel-1-quote-page-desktop.png", (0, 0, 2880, 1780), 1000),
    "quote-mobile": ("funnel-1-quote-page-mobile.png", (0, 0, 780, 1688), 340),
    "thanks-desktop": ("funnel-2-thank-you-desktop.png", (0, 0, 2880, 1780), 1000),
    "thanks-mobile": ("funnel-2-thank-you-mobile.png", (0, 0, 780, 1688), 340),
}
WORKFLOWS = {
    "wf1": "workflow-1-instant-lead-reply.png",
    "wf2": "workflow-2-missed-call-reply.png",
    "wf3": "workflow-3-quote-follow-up.png",
    "wf4": "workflow-4-stale-lead-alert.png",
}


def save_jpeg(im, dest, quality):
    im.save(dest, "JPEG", quality=quality, optimize=True, progressive=True, subsampling=0)


# ---------------------------------------------------------------------------------------------
# Workflow screenshot detection
# ---------------------------------------------------------------------------------------------

def _clusters(counts, gap):
    """Group the non-zero entries of a 1-D profile into [start, end) runs, bridging gaps <= gap."""
    idx = np.flatnonzero(counts > 0)
    out = []
    if not len(idx):
        return out
    s = p = int(idx[0])
    for i in idx[1:]:
        i = int(i)
        if i - p > gap:
            out.append((s, p + 1, int(counts[s:p + 1].sum())))
            s = i
        p = i
    out.append((s, p + 1, int(counts[s:p + 1].sum())))
    return out


def _runs(flags):
    out, s = [], None
    for i, v in enumerate(flags):
        if v and s is None:
            s = i
        elif not v and s is not None:
            out.append((s, i))
            s = None
    if s is not None:
        out.append((s, len(flags)))
    return out


def detect_workflow(path):
    """Find the parts of a GHL workflow-builder screenshot the deck needs, in source pixels.

    header_x:  x range of the header items to keep (workflow name + Builder/Settings/... tabs)
    nodes_x:   x range of the node column (trigger cards, actions, connectors, END)
    bounds:    widest x range a crop may use without catching other UI (Workflows list,
               Standard builder, avatar, Saved, Test workflow, zoom controls, Add, minimap)
    canvas:    (top, bottom) rows of the builder canvas
    bottom:    last row of workflow content (the END pill)
    """
    im = Image.open(path).convert("RGB")
    a = np.asarray(im)
    H, W, _ = a.shape
    mn = a.min(axis=2).astype(np.int16)

    # Canvas rows: the light-gray grid (min channel ~242-251) across the middle of the page.
    med = np.median(mn[:, W // 4: 3 * W // 4], axis=1)
    canvas_rows = (med >= 236) & (med < 253)
    runs = [r for r in _runs(canvas_rows) if r[1] - r[0] > H // 5]
    if not runs:
        raise RuntimeError(f"{path.name}: no builder canvas found")
    ct, cb = runs[0]

    # Header (everything above the canvas): drop full-width divider lines, then group columns.
    hdr = mn[:ct]
    divider = (hdr < 250).mean(axis=1) > 0.6
    hmask = (hdr < 240) & ~divider[:, None]
    hcl = _clusters(hmask.sum(axis=0), max(4, int(W * 0.015)))
    keep = [c for c in hcl if 0.3 * W <= (c[0] + c[1]) / 2 <= 0.7 * W]
    if not keep:
        raise RuntimeError(f"{path.name}: header row (name + tabs) not found")
    hx0, hx1 = min(c[0] for c in keep), max(c[1] for c in keep)
    other_h = [c for c in hcl if c not in keep]

    # Canvas ink: node text, card borders and connectors (min channel < 232; grid lines are >= 242).
    cm = mn[ct:cb] < 232
    ccl = _clusters(cm.sum(axis=0), max(4, int(W * 0.02)))
    central = [c for c in ccl if 0.25 * W <= (c[0] + c[1]) / 2 <= 0.75 * W]
    if not central:
        raise RuntimeError(f"{path.name}: node column not found")
    nodes = max(central, key=lambda c: c[2])
    other_c = [c for c in ccl if c is not nodes]

    lefts = [c[1] for c in other_h + other_c if c[1] <= min(hx0, nodes[0])]
    rights = [c[0] for c in other_h + other_c if c[0] >= max(hx1, nodes[1])]
    margin = int(W * 0.02)
    lo = (max(lefts) if lefts else 0) + margin
    hi = (min(rights) if rights else W) - margin

    rows = np.flatnonzero(cm[:, nodes[0]:nodes[1]].any(axis=1))
    bottom = ct + int(rows[-1]) + 1
    return {
        "im": im, "W": W, "H": H, "header_x": (hx0, hx1), "nodes_x": (nodes[0], nodes[1]),
        "bounds": (lo, hi), "canvas": (ct, cb), "bottom": bottom,
        "ink": cm, "pad": max(8, int(W * 0.015)),
    }


def _content_box(d):
    """Smallest crop (from the top, so the header row stays) that holds the header and all nodes."""
    pad = d["pad"]
    x0 = min(d["header_x"][0], d["nodes_x"][0]) - pad
    x1 = max(d["header_x"][1], d["nodes_x"][1]) + pad
    h = min(d["bottom"] + pad, d["canvas"][1] - 2)
    return x0, x1, h


def _max_aspect(d):
    """Widest aspect (w/h) a clean crop of this screenshot can have."""
    lo, hi = d["bounds"]
    return (hi - lo) / _content_box(d)[2]


def _fit_crop(d, aspect):
    """Crop with the given aspect ratio: header row at the top, END at the bottom, centred on the
    content, never reaching the other UI. Extra width shows more canvas below END."""
    lo, hi = d["bounds"]
    x0c, x1c, h = _content_box(d)
    w = h * aspect
    if w < x1c - x0c:
        w = x1c - x0c
        h = w / aspect
    h_max = d["canvas"][1] - 2
    if h > h_max:                       # cannot keep the aspect: keep everything, accept the ratio
        h = h_max
    w = min(w, hi - lo)
    cx = (x0c + x1c) / 2
    x0 = min(max(cx - w / 2, lo), hi - w)
    return (int(round(x0)), 0, int(round(x0 + w)), int(round(h)))


def plan_quote_split(d, avail):
    """Split the Quote Follow-Up canvas between two nodes so both halves show as large as possible.

    Panel a: header row + the first steps. Panel b: the remaining steps down to END.
    Returns (crop_a, crop_b, scale) where scale is CSS px per source px."""
    ct, cb = d["canvas"]
    pad = d["pad"]
    nx0, nx1 = d["nodes_x"]
    lo, hi = d["bounds"]
    # A row is quiet when its only ink is the vertical connector line (narrow extent), so a split
    # never cuts through a node card or a "+" button.
    band = d["ink"][:, nx0:nx1]
    has = band.any(axis=1)
    first = np.argmax(band, axis=1)
    last = band.shape[1] - 1 - np.argmax(band[:, ::-1], axis=1)
    quiet = ~has | ((last - first) <= max(6, int(d["W"] * 0.003)))
    gaps = [r for r in _runs(quiet) if r[1] - r[0] >= max(6, pad)]
    end = d["bottom"] + pad
    best = None
    for g0, g1 in gaps:
        split = ct + (g0 + g1) // 2
        if split <= ct + (end - ct) * 0.2 or split >= end - pad * 4:
            continue
        a_cols = np.flatnonzero(d["ink"][: split - ct].any(axis=0))
        b_cols = np.flatnonzero(d["ink"][split - ct: end - ct].any(axis=0)[nx0:nx1]) + nx0
        if not len(b_cols):
            continue
        hx0, hx1 = d["header_x"]
        a_cols = a_cols[(a_cols >= nx0) & (a_cols < nx1)]
        ax0 = min(hx0, int(a_cols.min())) - pad
        ax1 = max(hx1, int(a_cols.max()) + 1) + pad
        bx0, bx1 = int(b_cols.min()) - pad, int(b_cols.max()) + 1 + pad
        wa, ha = ax1 - ax0, split
        wb, hb = bx1 - bx0, end - split
        k = min(WF_IMG_H / ha, (avail - 2 * CHROME - ARROW_GAP) / (wa + wb), WF_IMG_H / hb)
        score = (round(k, 3), -abs(ha - hb))     # largest scale, then most even heights
        if best is None or score > best[0]:
            best = (score, k, (ax0, 0, ax1, split), (bx0, split, bx1, end))
    if best is None:
        raise RuntimeError("Quote Follow-Up: no gap between nodes to split at")
    _, k, (ax0, ay0, ax1, ay1), crop_b = best
    # Same scale for both panels, so equal source heights give equal panel heights (shared top
    # and bottom line). Panel a may only shrink from below; panel b may lose connector stub above
    # its first card and canvas below END, or gain canvas below END. No card or "+" is cut, and
    # END keeps END_CLEAR display px of clear canvas under it.
    clear = int(math.ceil(END_CLEAR / k))
    edge = int(math.ceil(CARD_CLEAR / k))
    rows = np.flatnonzero(~quiet) + ct
    a_min = int(rows[rows < ay1].max()) + 1 + edge
    b_first = int(rows[rows >= crop_b[1]].min())
    b_top_room = max(0, b_first - edge - crop_b[1])
    b_min = (d["bottom"] + clear) - (crop_b[1] + b_top_room)
    b_max = (cb - 2) - crop_b[1]
    h = min(ay1, b_max)
    if h < max(a_min, b_min):
        raise RuntimeError(f"Quote Follow-Up: cannot give both panels one height "
                           f"(a {a_min}..{ay1}, b {b_min}..{b_max})")
    ay1 = h
    crop_b_in = crop_b
    by0, by1 = crop_b[1], crop_b[3]
    trim = (by1 - by0) - h
    if trim > 0:                       # take half from the stub above, the rest from below END
        bot_room = by1 - (d["bottom"] + clear)
        top_cut = min(b_top_room, max(trim // 2, trim - bot_room))
        by0 += top_cut
        by1 -= trim - top_cut
    else:                              # show more canvas below END
        by1 += -trim
    crop_b = (crop_b[0], by0, crop_b[2], by1)
    print(f"wf3 split: height {h} src px, b trimmed {by0 - crop_b_in[1]} above the first card and "
          f"{crop_b_in[3] - by1} below END ({(by1 - d['bottom']) * k:.0f} display px clear under END)")
    # Use any spare width to show more canvas in panel a (keeps panel b on the right margin).
    spare = (avail - 2 * CHROME - ARROW_GAP) / k - (ax1 - ax0) - (crop_b[2] - crop_b[0])
    grow = max(0, min(spare, (hi - lo) - (ax1 - ax0)))
    cx = (ax0 + ax1) / 2
    w = (ax1 - ax0) + grow
    x0 = min(max(cx - w / 2, lo), hi - w)
    crop_a = (int(round(x0)), ay0, int(round(x0 + w)), ay1)
    return crop_a, crop_b, k


def prepare_workflows():
    det = {k: detect_workflow(FINAL / v) for k, v in WORKFLOWS.items()}
    singles = ["wf1", "wf2", "wf4"]
    # One frame for the three single-panel slides: as wide as the right column allows, but no
    # wider than the cleanest crop of every screenshot (no stray UI at the sides).
    a_box = (SLIDE_W - SIDE - TEXT_RIGHT - MIN_GAP - CHROME) / WF_IMG_H
    aspect = min([a_box] + [_max_aspect(det[k]) for k in singles])
    frame_w = int(round(WF_IMG_H * aspect)) + CHROME
    # Gap from the text column: equal to the space right of the panel, or the right margin.
    gap = max(MIN_GAP, (SLIDE_W - TEXT_RIGHT - frame_w) // 2)
    gap = min(gap, SLIDE_W - SIDE - TEXT_RIGHT - frame_w)
    panel_left = TEXT_RIGHT + gap
    css = ["/* Generated by build_deck.py from the screenshot crops. Do not edit by hand. */",
           f".s-wf .visual{{justify-content:flex-start;padding-left:{gap}px}}"]
    for k in singles:
        d = det[k]
        box = _fit_crop(d, aspect)
        im = d["im"].crop(box)
        save_jpeg(im, ASSETS / f"{k}.jpg", ASSET_QUALITY)
        w = int(round(WF_IMG_H * im.width / im.height))
        css.append(f".s-wf img.{k}{{width:{w}px;height:{WF_IMG_H}px}}")
        print(f"asset {k + '.jpg':20s} {im.width}x{im.height}  crop {box}  shown {w}x{WF_IMG_H}")

    # Quote Follow-Up: two panels sharing a top line, left edge where the other workflow panels sit.
    avail = SLIDE_W - SIDE - panel_left
    crop_a, crop_b, k = plan_quote_split(det["wf3"], avail)
    ima, imb = det["wf3"]["im"].crop(crop_a), det["wf3"]["im"].crop(crop_b)
    save_jpeg(ima, ASSETS / "wf3a.jpg", ASSET_QUALITY)
    save_jpeg(imb, ASSETS / "wf3b.jpg", ASSET_QUALITY)
    print(f"asset {'wf3a.jpg':20s} {ima.width}x{ima.height}  crop {crop_a}")
    print(f"asset {'wf3b.jpg':20s} {imb.width}x{imb.height}  crop {crop_b}")
    aw, ah = round(ima.width * k), round(ima.height * k)
    bw, bh = round(imb.width * k), round(imb.height * k)
    top = max(V_MARGIN, (SLIDE_H - (max(ah, bh) + CHROME)) // 2)
    a_right = panel_left + aw + CHROME
    b_left = SLIDE_W - SIDE - bw - CHROME
    arrow = 52
    arrow_x = round((a_right + b_left) / 2 - arrow / 2)
    arrow_y = round(top + (min(ah, bh) + CHROME) / 2 - arrow / 2)
    css += [f".s-wf3 .a{{left:{panel_left}px;top:{top}px}}",
            f".s-wf3 .a img{{width:{aw}px;height:{ah}px}}",
            f".s-wf3 .b{{left:{b_left}px;top:{top}px}}",
            f".s-wf3 .b img{{width:{bw}px;height:{bh}px}}",
            f".s-wf3 .next{{left:{arrow_x}px;top:{arrow_y}px}}"]
    LAYOUT_CSS.write_text("\n".join(css) + "\n")
    layout = {"aspect": round(aspect, 3), "panel_left": panel_left, "gap_text": gap,
              "a": [aw, ah], "b": [bw, bh], "top": top, "arrow": [arrow_x, arrow_y]}
    print("layout", json.dumps(layout))
    return layout


def prepare_assets():
    ASSETS.mkdir(exist_ok=True)
    for name, (src, box, display_w) in STATIC_SPECS.items():
        im = Image.open(FINAL / src).convert("RGB")
        if box:
            im = im.crop(box)
        if display_w:
            target_w = int(math.ceil(display_w * TARGET_DENSITY))
            if im.width > target_w:  # never upscale
                h = round(im.height * target_w / im.width)
                im = im.resize((target_w, h), Image.LANCZOS)
        dest = ASSETS / f"{name}.jpg"
        save_jpeg(im, dest, ASSET_QUALITY)
        print(f"asset {dest.name:20s} {im.width}x{im.height}  {dest.stat().st_size/1024:.0f} KB")
    return prepare_workflows()


# ---------------------------------------------------------------------------------------------
# Bake, print, preview
# ---------------------------------------------------------------------------------------------

PDFJS = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"
PDFJS_WORKER = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js"
WAIT_IMAGES = ("Array.from(document.images).filter(i => !i.classList.contains('bake'))"
               ".every(i => i.complete && i.naturalWidth > 0)")


def check_layout(browser):
    """Density, overflow and margin checks on the live (unbaked) layout."""
    page = browser.new_page(viewport={"width": SLIDE_W, "height": SLIDE_H})
    page.goto((HERE / "deck.html").as_uri(), wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    page.wait_for_function(WAIT_IMAGES)
    print("Figtree loaded:", page.evaluate("document.fonts.check('600 72px Figtree')"))
    report = page.evaluate(
        """() => {
          const imgs = Array.from(document.querySelectorAll('img')).filter(i => i.getClientRects().length).map(i => {
            const r = i.getBoundingClientRect();
            return {src: i.getAttribute('src'), nat: i.naturalWidth, shown: r.width,
                    density: +(i.naturalWidth / r.width).toFixed(2)};
          });
          const over = [], boxes = [];
          document.querySelectorAll('.slide').forEach((s, n) => {
            const sr = s.getBoundingClientRect();
            const rel = r => [r.left - sr.left, r.top - sr.top, r.right - sr.left, r.bottom - sr.top].map(Math.round);
            s.querySelectorAll('.panel, .phone, h1, h2, .sub, .eyebrow, .meta').forEach(el => {
              const r = el.getBoundingClientRect();
              if (r.left < sr.left - 1 || r.right > sr.right + 1 || r.top < sr.top - 1 || r.bottom > sr.bottom + 1)
                over.push({slide: n + 1, cls: el.className, r: rel(r)});
            });
            if (n > 0) s.querySelectorAll('.visual .panel, .visual .phone, .visual .next').forEach(el => {
              const r = el.getBoundingClientRect();
              boxes.push({slide: n + 1, cls: el.className, r: rel(r)});
            });
            const t = s.querySelector('.text').getBoundingClientRect();
            boxes.push({slide: n + 1, cls: 'text', r: rel(t)});
          });
          return {imgs, over, boxes, slides: document.querySelectorAll('.slide').length};
        }"""
    )
    page.close()
    for i in report["imgs"]:
        flag = "" if i["density"] >= MIN_DENSITY else "   <-- below 1.5x"
        print(f"img {i['src']:28s} natural {i['nat']:5d}  shown {i['shown']:7.1f}  density {i['density']}{flag}")
    problems = []
    if report["over"]:
        problems.append(("overflow", report["over"]))
    for b in report["boxes"]:
        x0, y0, x1, y1 = b["r"]
        print(f"box slide {b['slide']} {b['cls']:14s} {b['r']}")
        if b["cls"] == "text" or "next" in b["cls"]:
            continue
        if x1 > SLIDE_W - SIDE + 1:
            problems.append(("past right margin", b))
        if b["slide"] in (3, 4, 5, 6) and (y0 < 80 or y1 > SLIDE_H - 80):
            problems.append(("vertical margin under 80px", b))
    s5 = [b for b in report["boxes"] if b["slide"] == 5]
    pa = next(b["r"] for b in s5 if b["cls"].endswith(" a"))
    pb = next(b["r"] for b in s5 if b["cls"].endswith(" b"))
    nx = next(b["r"] for b in s5 if "next" in b["cls"])
    s3 = next(b["r"] for b in report["boxes"] if b["slide"] == 3 and "panel" in b["cls"])
    if pa[1] != pb[1]:
        problems.append(("slide 5 panels not on one top line", [pa, pb]))
    if abs(pa[3] - pb[3]) > 1:
        problems.append(("slide 5 panels not on one bottom line", [pa, pb]))
    if abs((nx[0] + nx[2]) / 2 - (pa[2] + pb[0]) / 2) > 1:
        problems.append(("slide 5 arrow not centred in the gap", [pa, nx, pb]))
    if abs(pa[0] - s3[0]) > 1:
        problems.append(("slide 5 left panel not aligned with the other workflow panels", [pa, s3]))
    print("slides in html:", report["slides"])
    for p in problems:
        print("LAYOUT PROBLEM:", json.dumps(p))
    return report["slides"], not problems


def bake_slides(browser):
    """Render each slide's visual layer at 2x with the text hidden: one 3840x2160 JPEG per slide.

    Chrome prints CSS blurred box-shadows as luminosity soft masks, which Apple's PDF engine
    (Preview, Quick Look, Safari, iOS) draws as solid gray boxes, and it rasterises the cover's
    3D-transformed layers at low resolution. Baking the visuals avoids both."""
    for old in ASSETS.glob("bake-*.jpg"):
        old.unlink()
    stale = ASSETS / "cover-stage.jpg"
    if stale.exists():
        stale.unlink()
    page = browser.new_page(viewport={"width": SLIDE_W, "height": SLIDE_H}, device_scale_factor=2)
    page.goto((HERE / "deck.html").as_uri(), wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    page.wait_for_function(WAIT_IMAGES)
    page.evaluate("document.documentElement.classList.add('baking')")
    slides = page.locator(".slide")
    total = 0
    for n in range(slides.count()):
        png = slides.nth(n).screenshot(type="png", animations="disabled")
        im = Image.open(io.BytesIO(png)).convert("RGB")
        if im.size != (SLIDE_W * 2, SLIDE_H * 2):
            raise RuntimeError(f"slide {n + 1} baked at {im.size}, expected 3840x2160")
        dest = ASSETS / f"bake-{n + 1:02d}.jpg"
        save_jpeg(im, dest, BAKE_QUALITY)
        total += dest.stat().st_size
        print(f"bake  {dest.name:20s} {im.width}x{im.height}  {dest.stat().st_size/1024:.0f} KB")
    print(f"bake total {total/1024/1024:.2f} MB")
    page.close()


def print_pdf(browser):
    page = browser.new_page(viewport={"width": SLIDE_W, "height": SLIDE_H})
    page.goto((HERE / "deck.html").as_uri(), wait_until="networkidle")
    page.evaluate("document.documentElement.classList.add('baked')")
    page.evaluate("document.fonts.ready")
    page.wait_for_function("Array.from(document.querySelectorAll('img.bake')).every(i => i.complete && i.naturalWidth > 0)")
    page.emulate_media(media="print")
    page.pdf(path=str(PDF_OUT), width=f"{SLIDE_W}px", height=f"{SLIDE_H}px",
             print_background=True, prefer_css_page_size=True)
    page.close()
    print(f"PDF {PDF_OUT}  {PDF_OUT.stat().st_size/1024/1024:.2f} MB")


def pdfjs_previews(browser):
    """Rasterise the actual PDF with pdf.js so the previews show what a browser viewer shows."""
    b64 = base64.b64encode(PDF_OUT.read_bytes()).decode()
    viewer = browser.new_page(viewport={"width": SLIDE_W, "height": SLIDE_H})
    viewer.set_content("<html><body style='margin:0'></body></html>")
    viewer.add_script_tag(url=PDFJS)
    pngs = viewer.evaluate(
        """async ([data, worker]) => {
          pdfjsLib.GlobalWorkerOptions.workerSrc = worker;
          const bytes = Uint8Array.from(atob(data), c => c.charCodeAt(0));
          const doc = await pdfjsLib.getDocument({data: bytes}).promise;
          const out = [];
          for (let n = 1; n <= doc.numPages; n++) {
            const pg = await doc.getPage(n);
            const vp1 = pg.getViewport({scale: 1});
            const vp = pg.getViewport({scale: 1920 / vp1.width});
            const c = document.createElement('canvas');
            c.width = Math.round(vp.width); c.height = Math.round(vp.height);
            await pg.render({canvasContext: c.getContext('2d'), viewport: vp}).promise;
            out.push({w: vp1.width, h: vp1.height, png: c.toDataURL('image/png').split(',')[1]});
          }
          return out;
        }""",
        [b64, PDFJS_WORKER],
    )
    viewer.close()
    for n, pg in enumerate(pngs, 1):
        (CHECK / f"slide-{n:02d}.png").write_bytes(base64.b64decode(pg["png"]))
    sizes = sorted({(round(pg["w"] * 4 / 3), round(pg["h"] * 4 / 3)) for pg in pngs})
    print(f"PDF pages: {len(pngs)}  page size(s) in CSS px: {sizes}")
    return len(pngs), sizes


# ---------------------------------------------------------------------------------------------
# Apple-engine check
# ---------------------------------------------------------------------------------------------

def _cg_write_png(cgimage, dest):
    import Quartz
    from Foundation import NSURL
    dst = Quartz.CGImageDestinationCreateWithURL(NSURL.fileURLWithPath_(str(dest)), "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(dst, cgimage, None)
    if not Quartz.CGImageDestinationFinalize(dst):
        raise RuntimeError(f"could not write {dest}")


def apple_previews():
    """Render every page with Apple's own PDF engine (CoreGraphics, what Preview, Quick Look and
    Safari use) into .check/apple-slide-NN.png, and every single-page split through Quick Look
    (qlmanage) into .check/apple-ql-NN.png."""
    import Quartz
    from Foundation import NSURL
    doc = Quartz.CGPDFDocumentCreateWithURL(NSURL.fileURLWithPath_(str(PDF_OUT)))
    count = Quartz.CGPDFDocumentGetNumberOfPages(doc)
    cs = Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB)
    tmp = Path(tempfile.mkdtemp(prefix="deck-ql-"))
    for n in range(1, count + 1):
        page = Quartz.CGPDFDocumentGetPage(doc, n)
        box = Quartz.CGPDFPageGetBoxRect(page, Quartz.kCGPDFMediaBox)
        scale = SLIDE_W / box.size.width
        w, h = SLIDE_W, int(round(box.size.height * scale))
        ctx = Quartz.CGBitmapContextCreate(None, w, h, 8, w * 4, cs, Quartz.kCGImageAlphaPremultipliedLast)
        Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
        Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, w, h))
        Quartz.CGContextSetInterpolationQuality(ctx, Quartz.kCGInterpolationHigh)
        Quartz.CGContextScaleCTM(ctx, scale, scale)
        Quartz.CGContextDrawPDFPage(ctx, page)
        _cg_write_png(Quartz.CGBitmapContextCreateImage(ctx), CHECK / f"apple-slide-{n:02d}.png")

        # Single-page split for Quick Look (it only thumbnails page 1).
        single = tmp / f"page-{n:02d}.pdf"
        pctx = Quartz.CGPDFContextCreateWithURL(NSURL.fileURLWithPath_(str(single)), box, None)
        Quartz.CGPDFContextBeginPage(pctx, None)
        Quartz.CGContextDrawPDFPage(pctx, page)
        Quartz.CGPDFContextEndPage(pctx)
        Quartz.CGPDFContextClose(pctx)
        del pctx
        subprocess.run(["qlmanage", "-t", "-s", str(SLIDE_W), "-o", str(tmp), str(single)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.move(str(tmp / f"page-{n:02d}.pdf.png"), str(CHECK / f"apple-ql-{n:02d}.png"))
    shutil.rmtree(tmp, ignore_errors=True)
    return count


def compare_renders(count):
    """Compare Apple and pdf.js renders block by block; a gray-box defect differs over large areas."""
    ok = True
    for n in range(1, count + 1):
        ref = np.asarray(Image.open(CHECK / f"slide-{n:02d}.png").convert("RGB")).astype(np.int16)
        for kind in ("apple-slide", "apple-ql"):
            im = Image.open(CHECK / f"{kind}-{n:02d}.png").convert("RGB")
            if im.size != (ref.shape[1], ref.shape[0]):
                im = im.resize((ref.shape[1], ref.shape[0]), Image.LANCZOS)
            diff = np.abs(np.asarray(im).astype(np.int16) - ref).mean(axis=2)
            hb, wb = diff.shape[0] // 24, diff.shape[1] // 24
            blocks = diff[: hb * 24, : wb * 24].reshape(hb, 24, wb, 24).mean(axis=(1, 3))
            bad = float((blocks > 12).mean())
            line_ok = bad < 0.005
            ok &= line_ok
            print(f"apple check page {n} {kind:11s} mean diff {diff.mean():5.2f}  "
                  f"blocks over 12: {bad * 100:5.2f}%  {'ok' if line_ok else 'MISMATCH'}")
    return ok


def pdf_structure_ok():
    raw = PDF_OUT.read_bytes()
    smask = raw.count(b"/SMask")
    print(f"PDF soft masks (/SMask): {smask}")
    return smask == 0


def main():
    CHECK.mkdir(exist_ok=True)
    for old in list(CHECK.glob("slide-*.png")) + list(CHECK.glob("apple-*.png")):
        old.unlink()
    prepare_assets()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        slides, layout_ok = check_layout(browser)
        bake_slides(browser)
        print_pdf(browser)
        pages, sizes = pdfjs_previews(browser)
        browser.close()
    no_smask = pdf_structure_ok()
    apple_pages = apple_previews()
    apple_ok = apple_pages == pages and compare_renders(apple_pages)
    mb = PDF_OUT.stat().st_size / 1024 / 1024
    ok = (pages == 8 and slides == 8 and sizes == [(SLIDE_W, SLIDE_H)] and mb < MAX_PDF_MB
          and layout_ok and no_smask and apple_ok)
    print("CHECK", "PASS" if ok else "FAIL",
          f"pages={pages} size={mb:.2f}MB layout={'ok' if layout_ok else 'FAIL'} "
          f"smask={'none' if no_smask else 'FOUND'} apple={'ok' if apple_ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
