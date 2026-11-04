#!/usr/bin/env python3
"""Box-only video pipeline. inbox -> review. Never posts anything.
Transcript: faster-whisper if installed, else sidecar <name>.srt next to the video, else no captions."""
import json, os, re, shutil, subprocess, datetime
from PIL import Image, ImageDraw, ImageFont
ROOT = os.path.expanduser("~/advero/state/content/video_drop")
BRAND = os.path.expanduser("~/advero/state/brand_kit")
QFILE = os.path.expanduser("~/advero/state/dashboard/live/pending_questions.json")
LOG = os.path.join(ROOT, "video_log.jsonl")
FONT = "/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf"
BLUE, INK = "#2f74f5", "#16202e"
FILLERS = {"um", "uh", "erm", "ah", "uhm", "hmm"}
FORMATS = {"4x5": (1080, 1350), "9x16": (1080, 1920), "1x1": (1080, 1080)}
VEXT = (".mp4", ".mov", ".m4v", ".mkv", ".webm")

def sh(*a): subprocess.run(a, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
def dur(p): return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",p]).strip())

def keep_segments(src, d):
    out = subprocess.run(["ffmpeg","-i",src,"-af","silencedetect=n=-35dB:d=0.6","-f","null","-"],stderr=subprocess.PIPE,text=True).stderr
    st = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    segs, cur = [], 0.0
    for s, e in zip(st, en + [d]*(len(st)-len(en))):
        if s - cur > 0.25: segs.append((cur, s + 0.15))
        cur = max(cur, e - 0.15)
    if d - cur > 0.25: segs.append((cur, d))
    return segs or [(0, d)]

def words_whisper(path):
    try: from faster_whisper import WhisperModel
    except ImportError: return None
    m = WhisperModel("small.en", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(path, word_timestamps=True)
    return [(w.start, w.end, w.word.strip()) for s in segs for w in s.words]

def words_srt(srt):
    if not os.path.exists(srt): return None
    ts = lambda t: sum(float(x)*y for x, y in zip(t.replace(",", ".").split(":"), (3600, 60, 1)))
    ws = []
    for blk in open(srt).read().strip().split("\n\n"):
        L = blk.strip().splitlines()
        if len(L) < 3: continue
        a, b = [ts(x.strip()) for x in L[1].split("-->")]
        toks = " ".join(L[2:]).split(); step = (b - a) / max(len(toks), 1)
        ws += [(a + i*step, a + (i+1)*step, t) for i, t in enumerate(toks)]
    return ws

def remap(words, segs):
    out, off = [], 0.0
    for a, b in segs:
        for s, e, w in words:
            if s >= a and e <= b + 0.05: out.append((s - a + off, min(e, b) - a + off, w))
        off += b - a
    return out

def ass(words, W, H, path):
    t = lambda x: "%d:%02d:%05.2f" % (x//3600, x%3600//60, x%60)
    fs = int(W * 0.065)
    hdr = ("[Script Info]\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 0\n\n[V4+ Styles]\n"
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
           "Style: C,Inter,%d,&H00FFFFFF,&H00FFFFFF,&H002E2016,&H80000000,1,0,0,0,100,100,0,0,1,5,2,2,60,60,%d,1\n\n[Events]\n"
           "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n") % (W, H, fs, int(H*0.2))
    lines, chunk = [], []
    def flush(chunk):
        for i, cw in enumerate(chunk):  # active word in brand light blue #6aa5ff
            txt = " ".join(("{\\c&HFFA56A&}" + x[2].upper() + "{\\c&HFFFFFF&}") if j == i else x[2].upper() for j, x in enumerate(chunk))
            end = chunk[i+1][0] if i+1 < len(chunk) else cw[1]
            lines.append("Dialogue: 0,%s,%s,C,,0,0,0,,%s" % (t(cw[0]), t(end), txt))
    for w in words:
        chunk.append(w)
        if len(chunk) == 3 or w[2][-1:] in ".?!,": flush(chunk); chunk = []
    if chunk: flush(chunk)
    open(path, "w").write(hdr + "\n".join(lines) + "\n")

def font(sz, bold=True):
    f = ImageFont.truetype(FONT, sz)
    try: f.set_variation_by_name("Bold" if bold else "Regular")
    except Exception: pass
    return f

def wrap(d, text, f, maxw):
    out, line = [], ""
    for w in text.split():
        tst = (line + " " + w).strip()
        if d.textlength(tst, font=f) > maxw and line: out.append(line); line = w
        else: line = tst
    return out + ([line] if line else [])

def end_card(W, H, path):
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    lk = Image.open(os.path.join(BRAND, "lockup-horizontal-glass-2400.png")).convert("RGBA")
    lk.thumbnail((int(W*0.75), H)); im.paste(lk, ((W-lk.width)//2, int(H*0.38)), lk)
    im.save(path)

def carousel(sentences, out_pdf, title):
    S, slides = 1080, []
    pts = [s for s in sentences if len(s.split()) > 3][:6] or [title]
    mark = Image.open(os.path.join(BRAND, "mark-glass-512.png")).convert("RGBA"); mark.thumbnail((110, 110))
    allt = [title] + pts + ["[CTA placeholder: Lorenzo writes or approves]"]
    for i, txt in enumerate(allt):
        im = Image.new("RGB", (S, S), BLUE if i == 0 else "white"); d = ImageDraw.Draw(im)
        col = "white" if i == 0 else INK; f = font(72 if i == 0 else 58)
        L = wrap(d, txt, f, S*0.8); y0 = S/2 - len(L)*f.size*0.65
        for j, l in enumerate(L): d.text((S*0.1, y0 + j*f.size*1.3), l, font=f, fill=col)
        im.paste(mark, (S-150, S-150), mark)
        d.text((S*0.1, S-110), "%d/%d" % (i+1, len(allt)), font=font(32, False), fill=col)
        slides.append(im)
    slides[0].save(out_pdf, save_all=True, append_images=slides[1:])
    slides[0].save(out_pdf.replace(".pdf", "_cover.png"))

def mc_item(name, outdir):
    try: q = json.load(open(QFILE))
    except Exception: q = []
    iid = "q-video-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not any(x.get("item_id") == iid for x in q):
        q.append({"item_id": iid, "bot": "Content Manager", "title": "Video ready: " + name,
                  "question": "Edited video (4:5, 9:16, 1:1), carousel and draft post are in " + outdir + ". Draft only, nothing posts without your yes.",
                  "options": ["Approve", "Edit", "Reject"]})
        tmp = QFILE + ".tmp"; json.dump(q, open(tmp, "w"), indent=1); os.replace(tmp, QFILE)
    return iid

def process(src):
    name = os.path.splitext(os.path.basename(src))[0]
    work = os.path.join(ROOT, "processing", name); os.makedirs(work, exist_ok=True)
    out = os.path.join(ROOT, "review", name); os.makedirs(out, exist_ok=True)
    srt = os.path.splitext(src)[0] + ".srt"
    raw = words_whisper(src) or words_srt(srt) or []
    segs = keep_segments(src, dur(src))
    norm = lambda w: re.sub(r"\W", "", w.lower())
    for s, e, w in raw:  # cut filler words out of the kept segments
        if norm(w) in FILLERS:
            segs = [p for a, b in segs for p in ([(a, s), (e, b)] if a < s < b else [(a, b)]) if p[1]-p[0] > 0.2]
    words = remap([w for w in raw if norm(w[2]) not in FILLERS], segs)
    fc = "".join("[0:v]trim=%f:%f,setpts=PTS-STARTPTS[v%d];[0:a]atrim=%f:%f,asetpts=PTS-STARTPTS[a%d];" % (a, b, i, a, b, i) for i, (a, b) in enumerate(segs))
    fc += "".join("[v%d][a%d]" % (i, i) for i in range(len(segs))) + "concat=n=%d:v=1:a=1[v][a];[a]loudnorm=I=-14:TP=-1.5,aresample=48000,aformat=channel_layouts=stereo[ao]" % len(segs)
    cut = os.path.join(work, "cut.mp4")
    sh("ffmpeg","-y","-i",src,"-filter_complex",fc,"-map","[v]","-map","[ao]","-r","30","-c:v","libx264","-preset","veryfast","-crf","18","-c:a","aac",cut)
    transcript = " ".join(w[2] for w in words)
    open(os.path.join(out, "transcript.txt"), "w").write(transcript or "(no transcript)")
    logo = os.path.join(BRAND, "mark-glass-512.png")
    for tag, (W, H) in FORMATS.items():
        a_ = os.path.join(work, tag + ".ass"); ass(words, W, H, a_)
        ec = os.path.join(work, "end_%s.png" % tag); end_card(W, H, ec)
        vf = ("[0:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,"
              "zoompan=z='if(mod(floor(it/5),2),1.12,1)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=%dx%d:fps=30,"
              "ass='%s'[b];[1:v]scale=%d:-1,format=rgba,colorchannelmixer=aa=0.85[l];"
              "[b][l]overlay=W-w-40:40,setsar=1,format=yuv420p[m];[2:v]scale=%d:%d,setsar=1,fps=30,format=yuv420p[e];"
              "[m][0:a][e][3:a]concat=n=2:v=1:a=1[v][a]") % (W, H, W, H, W, H, a_, int(W*0.1), W, H)
        sh("ffmpeg","-y","-i",cut,"-i",logo,"-loop","1","-t","2","-i",ec,"-f","lavfi","-t","2","-i","anullsrc=r=48000:cl=stereo",
           "-filter_complex",vf,"-map","[v]","-map","[a]","-c:v","libx264","-preset","veryfast","-crf","20","-c:a","aac","-movflags","+faststart",
           os.path.join(out, "%s_%s.mp4" % (name, tag)))
    sh("ffmpeg","-y","-ss","1.2","-i",os.path.join(out, name + "_4x5.mp4"),"-frames:v","1",os.path.join(out, "preview_4x5.png"))
    sents = [s.strip() for s in re.split(r"(?<=[.?!])\s+", transcript) if s.strip()]
    title = sents[0] if sents else name.replace("_", " ")
    carousel(sents[1:], os.path.join(out, "carousel.pdf"), title)
    open(os.path.join(out, "post_draft.md"), "w").write(
        "DRAFT for Lorenzo's review only. Never posted by a bot. Built from his own words in the video.\n\n## LinkedIn\n" + title + "\n\n" +
        "\n".join("- " + s for s in sents[1:5]) + "\n\n[CTA: Lorenzo writes or approves]\n\n## Community (Skool/Reddit)\n" + transcript + "\n")
    iid = mc_item(name, out)
    shutil.move(src, os.path.join(out, "raw" + os.path.splitext(src)[1]))
    if os.path.exists(srt): shutil.move(srt, os.path.join(out, "raw.srt"))
    shutil.rmtree(work, ignore_errors=True)
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "video": name, "segments": len(segs), "words": len(words), "out": out, "mc_item": iid}
    open(LOG, "a").write(json.dumps(rec) + "\n"); print(json.dumps(rec))
