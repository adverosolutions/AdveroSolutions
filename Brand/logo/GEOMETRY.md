# Advero Solutions mark "Depth": geometry (round 2)

All numbers are in the units of the 128 x 128 mark box (the viewBox of every `mark-*.svg`).
Generators: `kit/work/mark.py` (mark), `kit/work/wordmark.py` (outlines), `kit/work/build.py` (files),
`kit/work/render_png.py` (PNGs), `kit/work/gen2.py` (canvas artboards).

## Grid

- The 128 box is a 32 x 32 grid; 1 module = 4 units.
- At 16 px, 1 px = 8 units = 2 modules. Every edge of the flat geometry sits on that 8-unit grid, so it is pixel-sharp at 16, 32 and 64 px.
- Corner radius of every plane = side / 4.

## Two geometries, one silhouette box

Both geometries fill the same box: x 24 to 104, y 8 to 120 (80 x 112). The padding is 24 left and right and 8 top and bottom, and the box is centred on (64, 64). There is no extra optical shift: the heavy front plane at the bottom left is balanced by the reach of the back plane at the top right. This was checked in the 220 px app tile and in 160, 64 and 32 px circle crops.

### Glass (use at 64 px and up)

| plane | x | y | side | radius |
|---|---|---|---|---|
| front | 24 | 64 | 56 | 14 |
| mid   | 44 | 36 | 48 | 12 |
| back  | 64 | 8  | 40 | 10 |

- Step between top-left corners: 20 right and 28 up (5 : 7 modules), a climb of 54.5 degrees.
- Size falloff: 56, then 48, then 40 (2 modules less per step; x0.857, then x0.833).

### Flat and one-colour (use below 64 px; also every ink, white and flat file)

| plane | x | y | side | radius |
|---|---|---|---|---|
| front | 24 | 72 | 48 | 12 |
| mid   | 48 | 40 | 40 | 10 |
| back  | 72 | 8  | 32 | 8 |

- Step: 24 right and 32 up (3 : 4), a climb of 53.1 degrees. Size falloff: 48, then 40, then 32.
- Gap: 8 units (1 px at 16 px). Each plane behind is cut by the plane in front grown by 8 units. The cuts are real path booleans, not masks.
- At 16 px, every plane keeps at least a 1 px strip on the right and a 3 px strip on top, so all three shapes stay separate.

## Colours

- Glass front: linear gradient #6aa5ff to #2f74f5 (x1 .1, y1 0 to x2 .55, y2 1). Sheen on top: white .30, then .05 at 50%, then 0. Light edge: a 1.4-unit ring inset 0.7, white .98 at the top left fading to 0 by 30%, clear to 72%, then #c8daf2 at .55 at the bottom right.
- Glass mid: white .95 to #cfe0f8 .84 (translucent, so the back plane shows through). Glass back: #eef4fe to #b7cff3. Both have a hairline of #466eac at .36, 0.9 units wide, and the same light-edge ring (1.5 units, inset 0.9).
- Shadows between layers: #264880. The front plane's shadow falls on the mid plane with offset (2.4, 3.6); the mid plane's falls on the back plane with offset (2.2, 3.4). Softness is about 3.5 units, peak opacity about .5. Each shadow is 20 stacked translucent rounded rects clipped to the plane underneath, so there are no SVG filters in any file.
- Floor shadow: a radial-gradient ellipse, #34568c at .34 fading to 0, centred 3.2 units below the front plane (it stays inside the 128 box).
- Flat: front #2f74f5, mid #6aa5ff, back #b3cffa. Ink: #16202e. White: #ffffff.
- Wordmark: "Advero" ink #16202e, "Solutions" ink2 #4d596b. In white lockups: #ffffff, and #ffffff at fill-opacity .72. In ink lockups, both words are #16202e.

## Clear space

- Clear space = half the glass front plane = 28 units, measured at the scale where the mark box is 128.
- Horizontal lockup: the viewBox height is 128, so leave 28/128 = 0.22 x lockup height on every side. The viewBox already includes 8 units of padding, so leave 20 more outside it.
- Stacked lockup: the same 28 units in its own viewBox units (the mark is at 1 : 1), i.e. 0.146 x lockup height, of which 8 units are inside the viewBox.
- Mark alone: 28 units around the 80 x 112 silhouette box, which is 20 units beyond the file edge vertically and 4 units beyond it horizontally.

## Minimum sizes

- Glass mark: 64 px mark box. Below that, use the flat mark.
- Flat mark: 16 px.
- Horizontal lockup: glass when it is 64 px tall or more, otherwise flat, ink or white. Minimum 24 px tall (about 112 px wide); the cap height there is 8.4 px.
- Stacked lockup: minimum 120 px wide (68 px tall). Use flat below 96 px tall, where the mark box drops under 64 px.

## Lockup proportions

Wordmark: Figtree converted to outlines. "Advero" is weight 700 and "Solutions" 500, both instanced from the variable font with fontTools.varLib.instancer. Figtree's own GPOS kerning is applied through HarfBuzz. Letter-spacing is -0.03em (-30/1000 per glyph). There is a 0.26em word gap after the tracked "Advero" (matching the CSS lockup). Overlaps are removed with skia-pathops.

- **Horizontal** (viewBox 599.17 x 128). The mark box is 128 (the lockup height). The wordmark is set at 64 units (half the mark box), so the cap height is 44.8 and the mark silhouette (112) = 2.5 x cap height. The gap from the silhouette's right edge to the left edge of "A" is 32 units (0.71 x cap height). The cap height is centred vertically on the silhouette centre. There are 8 units of padding all round.
- **Stacked** (viewBox 339.93 x 192.25). The wordmark is set at 44 units (cap height 30.8, so the silhouette = 3.64 x cap height). There are 32 units from the silhouette's bottom to the top of the ascenders. The silhouette is centred horizontally over the wordmark's ink box. There are 8 units of padding all round.

## Files

- `svg/mark-{glass,flat,ink,white}.svg`: 128 x 128. The glass file has 8 gradient and clip ids prefixed `as-m-glass-`. The other files have no ids.
- `svg/lockup-{horizontal,stacked}-{glass,flat,ink,white}.svg`: glass ids are prefixed `as-lh-glass-` and `as-ls-glass-`.
- No `<style>`, fonts, filters, external references or `rgba()` in any file. Colours and opacities are plain attributes.
- `mark-glass-noshadow.svg` is not needed, because the glass shadows are filter-free.
- `png/`: mark-glass at 1024, 512 and 256; mark-flat at 64, 32 and 16; lockup-horizontal-glass and -white at 2400 x 513; lockup-stacked-glass at 1600 x 905. All have transparent backgrounds and were rendered by Chrome.
- `snippets.html`: inline markup for artboards. The glass snippet uses `PFX-` ids; the flat snippet has no ids.
