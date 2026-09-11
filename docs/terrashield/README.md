# TerraShield

AI-powered Earth observation and geospatial intelligence. An analyst-assistance
and monitoring system that turns satellite imagery into detections, changes,
deviations from a site's own history, and a ranked alert queue — each finding
carrying the evidence it rests on.

Built to the PRD in `TerraShield_AI.docx`, MVP scope (section 41): *AI Change
Intelligence*.

```bash
pip install -e ".[dev]"

terrashield --actor you@example.com demo            # the whole estate, end to end
terrashield --actor you@example.com queue           # what needs an analyst
terrashield --actor you@example.com ask "what changed at Mundra in the last 30 days"
terrashield evaluate                                # precision, recall, calibration
```

## What it does

**Detects objects**, and declares what the sensor could not have seen. A 4.5 m
car occupies a fifth of one Sentinel-2 pixel; no model recovers it, so the
detector returns the classes it refused to look for and why, rather than
returning zero and letting the analyst read that as "there were none".

**Detects change** between two scenes, after co-registering them, normalising
their radiometry, and estimating a noise floor that the changes themselves
cannot inflate. It refuses pairs it cannot legitimately difference — different
constellations, or SAR from different ground tracks — and says so instead of
producing a change map of the whole area.

**Learns each site's pattern of life** — robust medians with a weekday term —
and scores deviation from it. Never intent: the schema has nowhere to record a
motive and the copilot refuses questions that ask for one.

**Ranks alerts** on five dimensions (severity, confidence, novelty,
persistence, spatial reach), deduplicates by place and kind, and holds findings
that a single look cannot resolve.

**Carries evidence** with every finding: the scenes compared, the mask, the
baseline, the model version, and what could not be established. Evidence packs
are hash-chained and verify.

## Where things are

| Path | What it is |
|---|---|
| `src/terrashield/geo.py` | AOI geometry, local metre frames, GeoJSON |
| `src/terrashield/raster.py` | The image algebra, and a PNG encoder |
| `src/terrashield/world.py` | Ground truth for the demo estate — the pipeline never reads it |
| `src/terrashield/sensors.py` | The imaging model: resolution, cloud, speckle, sun angle |
| `src/terrashield/catalog.py` | Scene catalogue, revisit cadence, coverage; the `Provider` seam |
| `src/terrashield/sites.py` | Four real civilian sites, with scripted events |
| `src/terrashield/detect.py` | Object detection, and the resolution limits it declares |
| `src/terrashield/change.py` | Co-registration, normalisation, change detection |
| `src/terrashield/baseline.py` | Pattern of life |
| `src/terrashield/anomaly.py` | Deviation scoring, with its working |
| `src/terrashield/risk.py` | The five triage dimensions |
| `src/terrashield/alerts.py` | Declarative rules, deduplication, the queue |
| `src/terrashield/evidence.py` | Evidence bundles and verifiable packs |
| `src/terrashield/rbac.py` | Roles, permissions, the hash-chained audit log |
| `src/terrashield/store/` | SQLite persistence with tenant isolation in the SQL |
| `src/terrashield/pipeline.py` | Catalogue → alert, once per AOI per day |
| `src/terrashield/copilot.py` | Grounded question answering, with refusals |
| `src/terrashield/reports.py` | Daily, weekly and site reports |
| `src/terrashield/api.py` | The endpoints in PRD section 40 |
| `src/terrashield/evaluate.py` | Precision, recall, calibration — the measurement |
| `dashboard/terrashield/` | The console: map, queue, site pages, change viewer |
| `docs/terrashield/` | These notes |
| `tests/test_ts_*.py` | 142 tests, stdlib only |

## The demo estate

Four real places, all civilian infrastructure on public maps. That is a product
decision, not caution: PRD section 52 says not to open with a defence ministry,
and it is right — ports, solar parks and dams are where the dual-use market is,
they buy on a normal procurement cycle, and the change-detection problem is
identical. A demo built on somebody's air base makes the first sales
conversation about the demo instead of about the product.

| Area | Where | What it demonstrates |
|---|---|---|
| `IN-MUN-PORT` | Mundra, Gujarat | Maritime activity and terminal expansion |
| `IN-BHD-SOLAR` | Bhadla, Rajasthan | Construction progress on critical energy infrastructure |
| `IN-KCH-SECTOR` | Rann of Kutch | Remote-area monitoring against a near-empty background |
| `IN-SSD-DAM` | Sardar Sarovar | Reservoir extent, drawdown and refill |

Each carries scripted events on known dates — a new array block, a warehouse, a
track extension, a congestion episode, a drawdown. Those dates are the ground
truth the engines are scored against in `tests/test_ts_recovery.py`.

## The honest part

The demo imagery is modelled, not downloaded. `world.py` holds what is on the
ground and `sensors.py` renders it through a sensor model with real resolution,
real revisit cadence, real cloud climatology and real speckle. The engines never
see the truth; the tests measure how much of it they recovered.

That arrangement is worth more than a folder of real GeoTIFFs would be, because
it makes the product's claims *checkable*. Swapping in real imagery means
implementing `catalog.Provider` against Sentinel Hub, Planet or Maxar — one
module — and nothing above that line changes.

Measured numbers are in [03-measured-performance.md](03-measured-performance.md),
and `terrashield evaluate` reproduces them. They are specific to this estate:
re-run the same measurement against labelled customer scenes before quoting any
of them to a customer.

## Reading order

1. [01-prd-to-build.md](01-prd-to-build.md) — every PRD section, and what exists
2. [02-responsible-use.md](02-responsible-use.md) — the dual-use boundary, enforced in code
3. [03-measured-performance.md](03-measured-performance.md) — the numbers, and how to reproduce them
4. [04-deploying-for-real.md](04-deploying-for-real.md) — what changes when the imagery is real
