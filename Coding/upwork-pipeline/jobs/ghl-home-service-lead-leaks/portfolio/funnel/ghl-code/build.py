"""Build the paste-ready GHL Custom Code blocks and render local checks.

python3 build.py           -> step1.html, step3.html (paste each into its funnel step's Custom JS/HTML element)
python3 build.py --render  -> also .check/step{1,3}-{desktop,mobile}.png, rendered inside a mock GHL column
"""
import sys, pathlib

HERE = pathlib.Path(__file__).resolve().parent
FONT = '<link href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&display=swap" rel="stylesheet">'
common = (HERE / "common.css").read_text()

# a GHL-like wrapper (centred column with padding) so the full-bleed breakout gets tested too
MOCK = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{margin:0;font-family:Arial}.c-section{padding:20px 0}.c-row{max-width:1170px;margin:0 auto;padding:10px 5px}.c-column>.inner{padding:10px 5px}</style>
</head><body><div class="c-section"><div class="inner"><div class="c-row"><div class="inner"><div class="c-column"><div class="inner"><div class="c-code">%s</div></div></div></div></div></div></div></body></html>"""

for n in ("1", "3"):
    block = FONT + "\n<style>\n" + common + "</style>\n" + (HERE / f"step{n}.src.html").read_text()
    (HERE / f"step{n}.html").write_text(block)
    (HERE / ".check").mkdir(exist_ok=True)
    (HERE / ".check" / f"mock{n}.html").write_text(MOCK % block)
    print(f"step{n}.html", len(block), "chars")

if "--render" in sys.argv:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome")
        for n in ("1", "3"):
            for name, w, h in (("desktop", 1440, 900), ("mobile", 390, 844)):
                pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto((HERE / ".check" / f"mock{n}.html").as_uri(), wait_until="networkidle")
                pg.evaluate("document.fonts.ready")
                pg.wait_for_timeout(300)
                sw = pg.evaluate("document.documentElement.scrollWidth")
                pg.screenshot(path=str(HERE / ".check" / f"step{n}-{name}.png"), full_page=True)
                print(f"step{n}-{name}: scrollWidth {sw} (viewport {w})", errs or "")
                pg.close()
        b.close()
