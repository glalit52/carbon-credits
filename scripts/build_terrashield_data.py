"""Build the TerraShield console dataset from a monitored database.

Reads what the pipeline actually produced -- no recomputation of findings --
and re-renders the imagery behind the most significant change at each site so
the change viewer shows real pixels rather than an illustration.

    python3 scripts/build_terrashield_data.py --db terrashield.db \
        --out dashboard/terrashield

The one thing this script does recompute is the raster pair for the change
viewer, because rasters are not persisted: storing every scene would make the
database hundreds of megabytes, and the provider can reproduce any scene
exactly from its id. That is a property worth having anyway -- it means an
evidence bundle's scene reference is enough to regenerate the picture.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from terrashield import change, sites                       # noqa: E402
from terrashield.catalog import SyntheticProvider, coverage  # noqa: E402
from terrashield.domain import Role, SiteStatus              # noqa: E402
from terrashield.raster import render_overlay_png, render_png  # noqa: E402
from terrashield.store import Store                          # noqa: E402

STATUS_FOR = {
    SiteStatus.ANOMALOUS: "anomalous", SiteStatus.WATCH: "watch",
    SiteStatus.NORMAL: "normal", SiteStatus.STALE: "stale",
}


def provider() -> SyntheticProvider:
    p = SyntheticProvider()
    for s in sites.load_all():
        p.register(s.truth, s.climate)
    return p


def month_coverage(scenes) -> list[dict]:
    """Usable and rejected acquisitions by month. The honesty chart."""
    buckets: dict[str, dict] = {}
    for s in scenes:
        key = s.acquired_on.strftime("%Y-%m")
        b = buckets.setdefault(key, {"month": key, "usable": 0, "cloudy": 0,
                                     "sar": 0, "optical": 0})
        if s.usable:
            b["usable"] += 1
            b["sar" if s.sensor.value == "sar" else "optical"] += 1
        else:
            b["cloudy"] += 1
    return [buckets[k] for k in sorted(buckets)]


def chip_set(prov, aoi, event, out_dir: Path) -> dict | None:
    """Re-render the before/after pair behind one change event, plus its mask."""
    scenes = {s.id: s for s in prov.search(
        aoi, event.detected_at.date() - timedelta(days=120),
        event.detected_at.date())}
    before = scenes.get(event.before_scene_id)
    after = scenes.get(event.after_scene_id)
    if before is None or after is None:
        return None
    rb, ra = prov.fetch(aoi, before), prov.fetch(aoi, after)
    mb, ma = prov.masks(aoi, before, rb), prov.masks(aoi, after, ra)
    result = change.compare(aoi, before, after, rb, ra, mb.cloud, ma.cloud,
                            mb.water, ma.water)
    if result.mask is None:
        return None

    stem = event.id.replace(":", "_")
    names = {}
    for label, blob in (
        ("before", render_png(rb)),
        ("after", render_png(ra)),
        ("mask", render_overlay_png(ra, result.mask)),
    ):
        name = f"{stem}-{label}.png"
        (out_dir / name).write_bytes(blob)
        names[label] = f"chips/{name}"
    return {
        **names,
        "before_scene": before.id,
        "after_scene": after.id,
        "before_on": before.acquired_on.isoformat(),
        "after_on": after.acquired_on.isoformat(),
        "constellation": after.constellation.value,
        "sensor": after.sensor.value,
        "gsd_m": after.gsd_m,
        "width": rb.width, "height": rb.height,
        "registration_shift": list(result.registration_shift),
        "noise_floor": round(result.noise_floor, 5),
        "obscured_fraction": round(result.obscured_fraction, 4),
    }


def build(db_path: str, org_id: str, out: Path, as_of: date,
          chips_per_site: int = 2) -> dict:
    store = Store(db_path, org_id=org_id, actor="dashboard-build", role=Role.ADMIN)
    prov = provider()
    chips_dir = out / "chips"
    chips_dir.mkdir(parents=True, exist_ok=True)
    for old in chips_dir.glob("*.png"):
        old.unlink()

    window_start = as_of - timedelta(days=210)
    all_alerts = store.list_alerts(limit=1000)
    site_rows = []
    totals = Counter()

    for aoi in store.list_aois():
        scenes = store.list_scenes(aoi.id, window_start, as_of)
        changes = store.list_changes(aoi.id, start=window_start, end=as_of,
                                     limit=2000)
        anomalies = [a for a in store.list_anomalies(aoi.id, limit=2000)
                     if window_start <= a.observed_at.date() <= as_of]
        alerts = [a for a in all_alerts if a["aoi_id"] == aoi.id]
        cov = coverage(aoi.id, scenes, window_start, as_of)
        peak = max((a.score for a in anomalies), default=0.0)
        status = (SiteStatus.ANOMALOUS if peak >= 65
                  or any(a["priority"] <= 2 for a in alerts)
                  else SiteStatus.WATCH if alerts or peak >= 40
                  else SiteStatus.NORMAL)
        if cov.last_usable is None or (as_of - cov.last_usable).days > 21:
            status = SiteStatus.STALE

        notable = sorted(changes,
                         key=lambda e: (-e.severity.rank, -e.confidence, -e.area_m2))
        chips = []
        for event in notable[:chips_per_site]:
            c = chip_set(prov, aoi, event, chips_dir)
            if c:
                chips.append({
                    "change_id": event.id,
                    "type": event.change_type.value,
                    "severity": event.severity.value,
                    "confidence": event.confidence,
                    "area_m2": event.area_m2,
                    "detected_on": event.detected_at.date().isoformat(),
                    "explanation": event.explanation,
                    "evidence_id": event.evidence_id,
                    **c,
                })

        demo = next((d for d in sites.load_all() if d.id == aoi.id), None)
        totals["changes"] += len(changes)
        totals["alerts"] += len(alerts)
        totals["objects"] += len(store.list_detections(aoi.id, limit=100000))

        site_rows.append({
            "id": aoi.id, "name": aoi.name, "kind": aoi.kind.value,
            "country": aoi.country, "description": aoi.description,
            "area_km2": round(aoi.area_km2, 1),
            "centroid": [round(v, 5) for v in aoi.centroid],
            "bbox": [round(v, 5) for v in aoi.bbox],
            "fingerprint": aoi.fingerprint,
            "headline": demo.headline if demo else "",
            "status": STATUS_FOR[status],
            "peak_anomaly_score": round(peak, 1),
            "coverage": cov.to_dict(),
            "coverage_by_month": month_coverage(scenes),
            "change_count": len(changes),
            "alert_count": len(alerts),
            "changes": [
                {"id": e.id, "type": e.change_type.value,
                 "detected_on": e.detected_at.date().isoformat(),
                 "area_m2": e.area_m2, "confidence": e.confidence,
                 "severity": e.severity.value, "explanation": e.explanation,
                 "evidence_id": e.evidence_id,
                 "review_status": e.review_status.value}
                for e in notable[:40]],
            "anomalies": [
                {"date": a.observed_at.date().isoformat(), "score": a.score,
                 "confidence": a.confidence, "severity": a.severity.value,
                 "baseline_n": a.baseline_n, "reasons": a.reasons[:3]}
                for a in sorted(anomalies, key=lambda x: x.observed_at)],
            "chips": chips,
        })

    queue = sorted(all_alerts, key=lambda a: (a["priority"], a["created_at"]))
    intact, bad = store.verify_audit_chain()

    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of.isoformat(),
        "organisation": org_id,
        "window_days": 210,
        "totals": {
            "sites": len(site_rows),
            "alerts": len(all_alerts),
            "priority_1": sum(1 for a in all_alerts if a["priority"] == 1),
            "priority_2": sum(1 for a in all_alerts if a["priority"] == 2),
            "changes": totals["changes"],
            "objects": totals["objects"],
            "usable_scenes": sum(s["coverage"]["usable"] for s in site_rows),
            "acquired_scenes": sum(s["coverage"]["acquired"] for s in site_rows),
        },
        "audit": {"chain_intact": intact, "first_bad_entry": bad,
                  "entries": store.counts().get("audit_log", 0)},
        "sites": site_rows,
        "queue": [
            {"id": a["id"], "aoi_id": a["aoi_id"], "title": a["title"],
             "severity": a["severity"], "priority": a["priority"],
             "created_at": a["created_at"], "summary": a["summary"],
             "evidence_id": a["evidence_id"],
             "rule": (a.get("payload") or {}).get("rule_name", ""),
             "rule_text": (a.get("payload") or {}).get("rule", ""),
             "risk": (a.get("payload") or {}).get("risk") or {},
             "held": (a.get("payload") or {}).get("held_for_confirmation", ""),
             "review_status": a["review_status"]}
            for a in queue[:60]],
        "rules": [r.to_dict() for r in store.list_rules(enabled_only=False)],
    }
    return doc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="terrashield.db")
    p.add_argument("--org", default=sites.DEMO_ORG)
    p.add_argument("--out", default="dashboard/terrashield")
    p.add_argument("--as-of", default="")
    p.add_argument("--chips", type=int, default=2)
    args = p.parse_args(argv)

    as_of = (date.fromisoformat(args.as_of) if args.as_of
             else datetime.now(timezone.utc).date())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    doc = build(args.db, args.org, out, as_of, args.chips)
    (out / "data.json").write_text(json.dumps(doc, indent=1))
    size = (out / "data.json").stat().st_size
    print(f"wrote {out / 'data.json'} ({size / 1024:.0f} KB)")
    print(f"  {doc['totals']['sites']} sites, {doc['totals']['changes']} changes, "
          f"{doc['totals']['alerts']} alerts, "
          f"{len(list((out / 'chips').glob('*.png')))} imagery chips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
