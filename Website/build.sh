#!/usr/bin/env bash
# Builds a deployable copy of the site in Website/dist/.
# Copies the HTML pages and assets/, copies the brand files the pages use into dist/brand/,
# rewrites ../Brand/ links (brand/ in HTML, ../brand/ in assets/*.css), makes dist/404.html use
# root-absolute URLs so it works at any depth, and writes dist/CNAME. Touches nothing outside dist/.
set -euo pipefail

SITE="$(CDPATH= cd -- "$(dirname -- "$0")" >/dev/null && pwd)"
BRAND="$SITE/../Brand"
DIST="$SITE/dist"

case "$DIST" in
  */Website/dist) ;;
  *) echo "Refusing to build: unexpected dist path $DIST" >&2; exit 1 ;;
esac

rm -rf "$DIST"
mkdir -p "$DIST/brand"
echo "Fresh $DIST"

pages=0
for f in "$SITE"/*.html; do
  [ -e "$f" ] || continue
  cp "$f" "$DIST/"
  pages=$((pages + 1))
done
echo "Copied $pages HTML page(s)"

cp -R "$SITE/assets" "$DIST/assets"
echo "Copied assets/"

for d in tokens logo web; do
  if [ -d "$BRAND/$d" ]; then
    cp -R "$BRAND/$d" "$DIST/brand/$d"
    echo "Copied Brand/$d -> brand/$d"
  else
    echo "Skipped Brand/$d (not found)"
  fi
done

# HTML pages sit next to brand/; stylesheets in assets/ are one level down, so they need ../brand/.
rewritten=0
for f in "$DIST"/*.html; do
  [ -e "$f" ] || continue
  if grep -q '\.\./Brand/' "$f"; then
    perl -pi -e 's#\.\./Brand/#brand/#g' "$f"
    rewritten=$((rewritten + 1))
  fi
done
for f in "$DIST"/assets/*.css; do
  [ -e "$f" ] || continue
  if grep -q '\.\./Brand/' "$f"; then
    perl -pi -e 's#\.\./Brand/#../brand/#g' "$f"
    rewritten=$((rewritten + 1))
  fi
done
echo "Rewrote ../Brand/ links in $rewritten file(s) (brand/ in HTML, ../brand/ in CSS)"

# GitHub Pages serves 404.html at whatever path was requested (e.g. /a/b/c/missing), so every
# local href/src in the dist copy becomes root-absolute. #fragments, protocol URLs, mailto: and
# already-absolute paths are left alone.
if [ -e "$DIST/404.html" ]; then
  perl -pi -e 's#\b(href|src)="(?![a-zA-Z][a-zA-Z0-9+.-]*:|/|\#)([^"]+)"#$1="/$2"#g' "$DIST/404.html"
  echo "Made local URLs in 404.html root-absolute"
fi

# Brand/web/site.webmanifest lists its icons at the site root; on this site they live in /brand/web/.
# Fix the dist copy only and add the start_url and id the Brand README asks for.
MANIFEST="$DIST/brand/web/site.webmanifest"
if [ -e "$MANIFEST" ]; then
  python3 - "$MANIFEST" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as f:
    data = json.load(f)
for icon in data.get("icons", []):
    src = icon.get("src", "")
    if src.startswith("/") and not src.startswith("/brand/"):
        icon["src"] = "/brand/web/" + src.lstrip("/")
data.setdefault("start_url", "/")
data.setdefault("id", "/")
data = dict([("start_url", data.pop("start_url")), ("id", data.pop("id"))] + list(data.items()))
with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
  echo "Pointed site.webmanifest icons at /brand/web/ and set start_url and id"
fi

left="$(grep -l '\.\./Brand/' "$DIST"/*.html "$DIST"/assets/* 2>/dev/null || true)"
if [ -n "$left" ]; then
  echo "Still referencing ../Brand/: $left" >&2
  exit 1
fi

printf 'adverosolutions.com\n' > "$DIST/CNAME"
echo "Wrote CNAME (adverosolutions.com)"
echo "Done: $DIST"
