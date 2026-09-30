# Advero Solutions website

Static site for adverosolutions.com: the home page (with the six agent cards), about, a booking page with the GoHighLevel calendar, and a 404 page. Plain HTML, CSS and JS, no framework.

## Preview

Open `index.html` in a browser (no server needed), or build and serve `dist/` on this machine only:

```
./build.sh && python3 -m http.server 8000 --bind 127.0.0.1 --directory dist
```

then open http://127.0.0.1:8000/.

## Where things come from

- Colours, fonts, shadows and radii: `../Brand/tokens/brand.css`, loaded before `assets/site.css`. `site.css` uses only those tokens.
- Logos: `../Brand/logo/svg/`. If a logo file is missing, `assets/site.js` shows a text wordmark in its place until the file exists.
- Favicons and the social image: `../Brand/web/`.

## Build

```
./build.sh
```

This makes a fresh `dist/` with the pages, `assets/`, and the brand files copied into `dist/brand/`, rewrites every `../Brand/` link to `brand/`, makes the links in `dist/404.html` root-absolute (`/assets/…`, `/brand/…`, `/index.html`) so it works at any depth, and writes `dist/CNAME` with `adverosolutions.com`. It changes nothing outside `dist/`, and `dist/` is git-ignored.

## Deploy

Deploying `dist/` (for example to GitHub Pages with the CNAME above) is a separate step that Lorenzo approves. Nothing in this folder deploys on its own.
