"use client";

import { Crosshair, RotateCcw, Undo2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui";
import type { PolygonGeometry } from "@/lib/database.types";
import { measure, validate } from "@/lib/geo";
import type { T } from "@/lib/i18n";

export type Corner = { lon: number; lat: number; accuracy_m: number; at: string };

/** Accuracy above which marking a corner is discouraged (but not refused). */
const GOOD_M = 10;

export function ringOf(corners: Corner[]): PolygonGeometry | null {
  if (corners.length < 3) return null;
  const ring = corners.map((c) => [c.lon, c.lat]);
  return { type: "Polygon", coordinates: [[...ring, ring[0]]] };
}

/**
 * Walk the field and mark each corner. Needs GPS but no map tiles, so it
 * works where there is no data signal; the sketch is drawn from the corners.
 */
export function GpsWalk({ corners, onChange, t }: { corners: Corner[]; onChange: (c: Corner[]) => void; t: T }) {
  const [fix, setFix] = useState<GeolocationPosition | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [watching, setWatching] = useState(false);
  const watchId = useRef<number | null>(null);

  useEffect(() => () => {
    if (watchId.current != null) navigator.geolocation.clearWatch(watchId.current);
  }, []);

  function start() {
    if (!("geolocation" in navigator)) {
      setError(t("boundary.no_gps"));
      return;
    }
    setWatching(true);
    watchId.current = navigator.geolocation.watchPosition(
      (p) => {
        setFix(p);
        setError(null);
      },
      () => setError(t("boundary.no_gps")),
      { enableHighAccuracy: true, maximumAge: 0, timeout: 30_000 },
    );
  }

  const accuracy = fix?.coords.accuracy ?? null;
  const geometry = ringOf(corners);
  const problems = geometry ? validate(geometry) : [];
  const area = geometry && !problems.length ? measure(geometry).area_ha : null;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm">{t("boundary.help")}</p>
      <Sketch corners={corners} here={fix ? { lon: fix.coords.longitude, lat: fix.coords.latitude } : null} />
      <div className="grid grid-cols-3 gap-2 text-center text-sm">
        <div className="rounded-lg bg-surface-2 p-2">
          <div className="text-xs text-muted">{t("boundary.corners")}</div>
          <div className="text-lg font-semibold tabular">{corners.length}</div>
        </div>
        <div className="rounded-lg bg-surface-2 p-2">
          <div className="text-xs text-muted">{t("boundary.accuracy")}</div>
          <div className={`text-lg font-semibold tabular ${accuracy != null && accuracy > GOOD_M ? "text-accent" : ""}`}>
            {accuracy == null ? "—" : `${Math.round(accuracy)} m`}
          </div>
        </div>
        <div className="rounded-lg bg-surface-2 p-2">
          <div className="text-xs text-muted">{t("boundary.area")}</div>
          <div className="text-lg font-semibold tabular">{area == null ? "—" : `${area.toFixed(2)} ha`}</div>
        </div>
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
      {watching && accuracy != null && accuracy > GOOD_M && <p className="text-sm text-accent">{t("boundary.weak")}</p>}
      {problems.length > 0 && <p className="text-sm text-danger">{problems.join("; ")}</p>}
      {!watching ? (
        <Button type="button" onClick={start} className="py-4 text-base">
          <Crosshair className="h-5 w-5" /> {t("boundary.start")}
        </Button>
      ) : (
        <Button
          type="button"
          disabled={!fix}
          className="py-4 text-base"
          onClick={() =>
            fix &&
            onChange([
              ...corners,
              {
                lon: fix.coords.longitude,
                lat: fix.coords.latitude,
                accuracy_m: fix.coords.accuracy,
                at: new Date(fix.timestamp).toISOString(),
              },
            ])
          }
        >
          <Crosshair className="h-5 w-5" /> {fix ? t("boundary.add") : t("boundary.wait")}
        </Button>
      )}
      {corners.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          <Button type="button" variant="secondary" onClick={() => onChange(corners.slice(0, -1))}>
            <Undo2 className="h-4 w-4" /> {t("boundary.undo")}
          </Button>
          <Button type="button" variant="ghost" onClick={() => onChange([])}>
            <RotateCcw className="h-4 w-4" /> {t("boundary.clear")}
          </Button>
        </div>
      )}
    </div>
  );
}

/** The walked outline, scaled to fit, in local metres. */
function Sketch({ corners, here }: { corners: Corner[]; here: { lon: number; lat: number } | null }) {
  const pts = [...corners, ...(here ? [{ ...here, accuracy_m: 0, at: "" }] : [])];
  if (!pts.length) return <div className="h-48 rounded-xl border border-dashed border-border bg-surface" />;
  const lat0 = pts[0].lat;
  const kx = 111_320 * Math.cos((lat0 * Math.PI) / 180);
  const ky = 110_540;
  const xy = pts.map((p) => [(p.lon - pts[0].lon) * kx, -(p.lat - pts[0].lat) * ky]);
  const xs = xy.map((p) => p[0]);
  const ys = xy.map((p) => p[1]);
  const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 20);
  const pad = span * 0.12;
  const view = `${Math.min(...xs) - pad} ${Math.min(...ys) - pad} ${span + 2 * pad} ${span + 2 * pad}`;
  const walked = xy.slice(0, corners.length);
  const stroke = span / 120;
  return (
    <svg viewBox={view} className="h-48 w-full rounded-xl border border-border bg-surface" role="img" aria-label="Boundary sketch">
      {walked.length >= 3 && (
        <polygon points={walked.map((p) => p.join(",")).join(" ")} fill="var(--brand-soft)" stroke="none" />
      )}
      <polyline points={walked.map((p) => p.join(",")).join(" ")} fill="none" stroke="var(--brand)" strokeWidth={stroke * 2} />
      {walked.map((p, i) => (
        <g key={i}>
          <circle cx={p[0]} cy={p[1]} r={stroke * 4} fill="var(--brand)" stroke="var(--surface)" strokeWidth={stroke} />
          <text x={p[0] + stroke * 6} y={p[1] - stroke * 6} fontSize={stroke * 10} fill="var(--text)">
            {i + 1}
          </text>
        </g>
      ))}
      {here && (
        <circle cx={xy.at(-1)![0]} cy={xy.at(-1)![1]} r={stroke * 4} fill="var(--info)" stroke="var(--surface)" strokeWidth={stroke} />
      )}
    </svg>
  );
}
