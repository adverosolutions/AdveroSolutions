# Usage: python3 render.py <file.dc.html> <out.png> <width> <height> [scale]
# Renders an artboard's static markup in local Chrome at its exact size.
import asyncio, os, sys
from playwright.async_api import async_playwright
async def main(src, out, w, h, scale):
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='chrome')
        pg = await b.new_page(viewport={'width': w, 'height': h}, device_scale_factor=scale)
        await pg.goto('file://' + os.path.abspath(src))
        await pg.evaluate("document.fonts.ready.then(()=>1)")
        await pg.wait_for_timeout(1500)
        await pg.screenshot(path=out, clip={'x': 0, 'y': 0, 'width': w, 'height': h})
        await b.close()
a = sys.argv
asyncio.run(main(a[1], a[2], int(a[3]), int(a[4]), float(a[5]) if len(a) > 5 else 1))
