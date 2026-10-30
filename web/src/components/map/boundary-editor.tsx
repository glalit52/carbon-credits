"use client";

import { Crosshair, FileUp, Footprints, PenLine, Trash2, Type } from "lucide-react";
import { maplibregl } from "./maplibre";
import type { Map as MLMap } from "maplibre-gl";
import { TerraDraw, TerraDrawPolygonMode, TerraDrawSelectMode } from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button, Notice, Textarea, cx } from "@/components/ui";
import type { PolygonGeometry } from "@/lib/database.types";
import { BoundaryError, measure, parseBoundaryFile, parseLatLonList, validate } from "@/lib/geo";

import { baseStyle } from "./base-style";

type Tab = "draw" | "walk" | "paste" | "upload";
type Corner = { lat: number; lon: number; accuracy: number };

const TABS: { id: Tab; label: string; icon: typeof PenLine }[] = [
  { id: "draw", label: "Draw on map", icon: PenLine },
  { id: "walk", label: "Walk with GPS", icon: Footprints },
  { id: "paste", label: "Paste points", icon: Type },
  { id: "upload", label: "Upload file", icon: FileUp },
];

/**
 * Four ways to give a farm its boundary, one result: a validated polygon in
 * a hidden `boundary` input. Whatever the source, the shape lands on the map
 * where it can be corrected by dragging its corners.
 */
export function BoundaryEditor({
  initial,
  name = "boundary",
  center,
}: {
  initial?: PolygonGeometry | null;
  name?: string;
  center?: [number, number];
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const draw = useRef<TerraDraw | null>(null);
  const [tab, setTab] = useState<Tab>("draw");
  const [geometry, setGeometry] = useState<PolygonGeometry | null>(initial ?? null);
  const [message, setMessage] = useState<string | null>(null);
  const [paste, setPaste] = useState("");
  const [corners, setCorners] = useState<Corner[]>([]);
  const [fix, setFix] = useState<Corner | null>(null);
  const [walking, setWalking] = useState(false);
  const watch = useRef<number | null>(null);

  const problems = useMemo(() => (geometry ? validate(geometry) : []), [geometry]);
  const measured = useMemo(() => (geometry && !problems.length ? measure(geometry) : null), [geometry, problems]);

  const showOnMap = useCallback((g: PolygonGeometry) => {
    const d = draw.current;
    const m = map.current;
    if (!d || !m) return;
    d.clear();
    const polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
    d.addFeatures(
      polys.map((coordinates) => ({
        type: "Feature" as const,
        geometry: { type: "Polygon" as const, coordinates },
        properties: { mode: "polygon" },
      })),
    );
    d.setMode("select");
    const pts = polys.flat(2) as unknown as number[][];
    const xs = pts.map((p) => p[0]);
    const ys = pts.map((p) => p[1]);
    m.fitBounds([[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]], { padding: 50, maxZoom: 18, duration: 0 });
  }, []);

  const readSnapshot = useCallback(() => {
    const polys = (draw.current?.getSnapshot() ?? [])
      .filter((f) => f.geometry.type === "Polygon")
      .map((f) => f.geometry.coordinates as number[][][]);
    if (polys.length === 0) setGeometry(null);
    else if (polys.length === 1) setGeometry({ type: "Polygon", coordinates: polys[0] });
    else setGeometry({ type: "MultiPolygon", coordinates: polys });
  }, []);

  useEffect(() => {
    if (!el.current) return;
    const m = new maplibregl.Map({
      container: el.current,
      style: baseStyle("satellite"),
      center: center ?? [78.5, 12],
      zoom: center ? 15 : 4,
      attributionControl: { compact: true },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.current = m;
    m.once("load", () => {
      const d = new TerraDraw({
        adapter: new TerraDrawMapLibreGLAdapter({ map: m }),
        modes: [
          new TerraDrawPolygonMode({
            styles: { fillColor: "#49d18a", outlineColor: "#ffffff", outlineWidth: 2, fillOpacity: 0.3 },
          }),
          new TerraDrawSelectMode({
            flags: {
              polygon: {
                feature: { draggable: false, coordinates: { midpoints: true, draggable: true, deletable: true } },
              },
            },
            styles: { selectedPolygonColor: "#49d18a", selectedPolygonOutlineColor: "#ffffff", selectedPolygonFillOpacity: 0.3 },
          }),
        ],
      });
      d.start();
      d.setMode("polygon");
      d.on("finish", () => {
        readSnapshot();
        d.setMode("select");
      });
      d.on("change", (_ids, type) => {
        if (type === "update" || type === "delete") readSnapshot();
      });
      draw.current = d;
      if (initial) showOnMap(initial);
    });
    return () => {
      draw.current?.stop();
      draw.current = null;
      m.remove();
      map.current = null;
    };
    // The map is created once; later boundaries arrive through showOnMap.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(
    () => () => {
      if (watch.current !== null) navigator.geolocation.clearWatch(watch.current);
    },
    [],
  );

  function accept(g: PolygonGeometry, note?: string) {
    setGeometry(g);
    setMessage(note ?? null);
    showOnMap(g);
  }

  function clear() {
    draw.current?.clear();
    draw.current?.setMode("polygon");
    setGeometry(null);
    setMessage(null);
    setCorners([]);
  }

  function locateMe() {
    navigator.geolocation.getCurrentPosition(
      (p) => map.current?.flyTo({ center: [p.coords.longitude, p.coords.latitude], zoom: 17 }),
      (e) => setMessage(`Location unavailable: ${e.message}`),
      { enableHighAccuracy: true, timeout: 15000 },
    );
  }

  function startWalk() {
    if (!("geolocation" in navigator)) {
      setMessage("This device has no GPS access in the browser.");
      return;
    }
    setWalking(true);
    watch.current = navigator.geolocation.watchPosition(
      (p) => setFix({ lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy }),
      (e) => setMessage(`GPS error: ${e.message}`),
      { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 },
    );
  }

  function addCorner() {
    if (!fix) return;
    setCorners((c) => [...c, fix]);
    map.current?.flyTo({ center: [fix.lon, fix.lat], zoom: 18 });
  }

  function finishWalk() {
    if (corners.length < 3) {
      setMessage("Walk at least three corners before finishing.");
      return;
    }
    if (watch.current !== null) navigator.geolocation.clearWatch(watch.current);
    watch.current = null;
    setWalking(false);
    const worst = Math.max(...corners.map((c) => c.accuracy));
    const ring = corners.map((c) => [Math.round(c.lon * 1e7) / 1e7, Math.round(c.lat * 1e7) / 1e7]);
    accept(
      { type: "Polygon", coordinates: [[...ring, ring[0]]] },
      worst > 10
        ? `GPS accuracy was as poor as ${Math.round(worst)} m at one corner. Check the shape against the imagery and drag corners to fix it.`
        : undefined,
    );
  }

  function usePasted() {
    try {
      const [p] = parseLatLonList(paste);
      accept(p.geometry);
    } catch (e) {
      setMessage(e instanceof BoundaryError ? e.message : String(e));
    }
  }

  async function onFile(file: File) {
    try {
      const parsed = parseBoundaryFile(await file.text(), file.name);
      accept(
        parsed[0].geometry,
        parsed.length > 1
          ? `${file.name} holds ${parsed.length} polygons; this used the first. To add them all as separate farms, use Import data.`
          : undefined,
      );
    } catch (e) {
      setMessage(e instanceof BoundaryError ? e.message : `Could not read ${file.name}: ${String(e)}`);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <input type="hidden" name={name} value={geometry && !problems.length ? JSON.stringify(geometry) : ""} />
      <div className="flex flex-wrap gap-1 rounded-lg bg-surface-2 p-1">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cx(
              "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium sm:text-sm",
              tab === id ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text",
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      <div className="relative h-[420px] overflow-hidden rounded-xl border border-border">
        <div ref={el} className="h-full w-full" />
        <div className="absolute left-2 top-2 flex gap-1">
          <Button type="button" variant="secondary" className="px-2 py-1 text-xs shadow" onClick={locateMe}>
            <Crosshair className="h-3.5 w-3.5" /> My location
          </Button>
          {geometry && (
            <Button type="button" variant="secondary" className="px-2 py-1 text-xs shadow" onClick={clear}>
              <Trash2 className="h-3.5 w-3.5" /> Start over
            </Button>
          )}
        </div>
      </div>

      {tab === "draw" && (
        <p className="text-xs text-muted">
          Click each corner of the field on the imagery; click the first corner again to close it. Drag corners
          afterwards to correct them.
        </p>
      )}

      {tab === "walk" && (
        <div className="flex flex-col gap-2 rounded-lg border border-border p-3 text-sm">
          <p className="text-xs text-muted">
            Stand at a corner, wait for the accuracy to settle under 10 m, tap “Add corner”, walk to the next one.
          </p>
          {!walking ? (
            <Button type="button" variant="secondary" onClick={startWalk}>
              Start GPS
            </Button>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <span className={cx("text-xs", fix && fix.accuracy <= 10 ? "text-brand" : "text-accent")}>
                {fix ? `±${Math.round(fix.accuracy)} m` : "Waiting for a fix…"}
              </span>
              <Button type="button" onClick={addCorner} disabled={!fix}>
                Add corner ({corners.length})
              </Button>
              <Button type="button" variant="secondary" onClick={finishWalk} disabled={corners.length < 3}>
                Finish boundary
              </Button>
            </div>
          )}
        </div>
      )}

      {tab === "paste" && (
        <div className="flex flex-col gap-2">
          <Textarea
            rows={5}
            value={paste}
            onChange={(e) => setPaste(e.target.value)}
            placeholder={"One corner per line, latitude first:\n10.7867, 79.1378\n10.7868, 79.1398\n10.7878, 79.1396"}
          />
          <Button type="button" variant="secondary" onClick={usePasted} disabled={!paste.trim()}>
            Use these points
          </Button>
        </div>
      )}

      {tab === "upload" && (
        <label className="flex cursor-pointer flex-col items-center gap-1 rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm hover:bg-surface-2">
          <FileUp className="h-5 w-5 text-muted" />
          <span className="font-medium">Choose a KML, GeoJSON, WKT or text file</span>
          <span className="text-xs text-muted">Google Earth, QGIS and most field apps export one of these.</span>
          <input
            type="file"
            accept=".kml,.geojson,.json,.wkt,.txt,.csv"
            className="sr-only"
            onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
          />
        </label>
      )}

      {message && <Notice tone="accent">{message}</Notice>}
      {geometry && problems.length > 0 && (
        <Notice tone="danger" title="This boundary cannot be saved yet">
          <ul className="list-disc pl-4">
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </Notice>
      )}
      {measured && (
        <div className="flex flex-wrap gap-x-6 gap-y-1 rounded-lg bg-brand-soft px-4 py-2.5 text-sm text-brand-strong">
          <span>
            <strong className="tabular">{measured.area_ha.toFixed(2)} ha</strong> ({(measured.area_ha * 2.471).toFixed(2)} acres)
          </span>
          <span className="tabular">
            centre {measured.centroid_lat.toFixed(5)}, {measured.centroid_lon.toFixed(5)}
          </span>
        </div>
      )}
    </div>
  );
}
