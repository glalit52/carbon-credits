#!/usr/bin/env bash
# Assemble the static site Vercel serves.
#
# Deliberately a copy, not a rebuild. Regenerating the dashboard needs Python
# and a deterministic run of the feed; doing that inside a deploy would make
# the published page depend on whatever the build container happens to have.
# The page is built and reviewed locally, committed, and shipped as-is.
set -euo pipefail

rm -rf public
mkdir -p public

cp dashboard/index.html public/index.html
cp dashboard/data.json  public/data.json

# The evidence packs are the point of the product, so publish them where a
# verifier can be pointed at a URL rather than sent a zip.
if [ -d dashboard/packs ]; then
  cp -r dashboard/packs public/packs
fi

# The TerraShield console, with its imagery chips. Same rule as above: built
# and reviewed locally, committed, shipped as-is. Rebuilding it in a deploy
# would mean running six months of the monitoring pipeline inside the build
# container, which takes hours and would make the published page depend on
# whatever that container happened to have.
if [ -f dashboard/terrashield/index.html ]; then
  mkdir -p public/terrashield
  cp dashboard/terrashield/index.html public/terrashield/index.html
  cp dashboard/terrashield/data.json  public/terrashield/data.json
  if [ -d dashboard/terrashield/chips ]; then
    cp -r dashboard/terrashield/chips public/terrashield/chips
  fi
fi

cat > public/robots.txt <<'EOF'
User-agent: *
Disallow: /
EOF

echo "public/ assembled:"
find public -type f | sort | sed 's/^/  /'
