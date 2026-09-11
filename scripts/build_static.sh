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

cat > public/robots.txt <<'EOF'
User-agent: *
Disallow: /
EOF

echo "public/ assembled:"
find public -type f | sort | sed 's/^/  /'
