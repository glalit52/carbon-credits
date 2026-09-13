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

# The Personal AI CIO dashboard is a separate product in this repository and
# publishes under /cio. Same rule as above: built and reviewed locally,
# committed, shipped as-is.
if [ -d aicio_dashboard ]; then
  mkdir -p public/cio
  cp aicio_dashboard/index.html public/cio/index.html
  cp aicio_dashboard/data.json  public/cio/data.json
fi

cat > public/robots.txt <<'EOF'
User-agent: *
Disallow: /
EOF

echo "public/ assembled:"
find public -type f | sort | sed 's/^/  /'
