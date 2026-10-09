"""Render the Lead Leak Audit PNGs. Run: python3 render.py [--check]
audit-full.png at 1440 wide x2, and the three 1000x750 x2 portfolio frames.
--check also writes 390px and dark-theme checks to ./.check/ and reports console errors and overflow."""
import sys, pathlib
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
URL = (HERE / "audit.html").as_uri()
CHECK = "--check" in sys.argv

OVERFLOW_JS = """() => {
  const out = [];
  if (document.documentElement.scrollWidth > innerWidth + 1) out.push('page scrolls sideways: ' + document.documentElement.scrollWidth);
  document.querySelectorAll('body *').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || el.closest('svg')) return;
    if (el.scrollWidth > el.clientWidth + 1 && ['hidden','clip'].includes(cs.overflowX) && el.clientWidth > 0 && !el.classList.contains('haze'))
      out.push('clipped: ' + el.className + ' "' + (el.textContent || '').trim().slice(0, 40) + '"');
  });
  return out;
}"""


def shoot(pw, url, path, w, h, full, errors):
    b = pw.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
    pg.on("console", lambda m: m.type == "error" and errors.append(f"{path.name}: {m.text}"))
    pg.on("pageerror", lambda e: errors.append(f"{path.name}: {e}"))
    pg.goto(url, wait_until="networkidle")
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(400)
    issues = pg.evaluate(OVERFLOW_JS)
    pg.screenshot(path=str(path), full_page=full)
    b.close()
    return issues


with sync_playwright() as pw:
    errors, report = [], {}
    report["audit-full"] = shoot(pw, URL + "?static&theme=light", HERE / "audit-full.png", 1440, 900, True, errors)
    for fr in ("cover", "leaks", "fixes"):
        report[fr] = shoot(pw, URL + f"?frame={fr}&theme=light", HERE / f"audit-{fr}.png", 1000, 750, False, errors)
    if CHECK:
        c = HERE / ".check"; c.mkdir(exist_ok=True)
        report["m390"] = shoot(pw, URL + "?static&theme=light", c / "m390.png", 390, 844, True, errors)
        report["dark"] = shoot(pw, URL + "?static&theme=dark", c / "dark.png", 1440, 900, True, errors)
        report["m390dark"] = shoot(pw, URL + "?static&theme=dark", c / "m390dark.png", 390, 844, True, errors)
        report["live"] = shoot(pw, URL, c / "live.png", 1440, 900, False, errors)
    for k, v in report.items():
        print(k, "OK" if not v else v)
    print("console errors:", errors or "none")
