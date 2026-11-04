"use client";

import { maplibregl } from "./maplibre";
import type { GeoJSONSource, Map as MLMap } from "maplibre-gl";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type { PolygonGeometry } from "@/lib/database.types";

import { baseStyle } from "./base-style";

export type MapFarm = {
  id: string;
  name: string;
  boundary: PolygonGeometry;
  status: string;
  area_ha: number;
};

const STATUS_COLOR = ["match", ["get", "status"], "draft", "#e0a64a", "blocked", "#f2705f", "withdrawn", "#97a59b", "#49d18a"];

function bounds(farms: MapFarm[]): [[number, number], [number, number]] | null {
  let minX = 180, minY = 90, maxX = -180, maxY = -90;
  for (const f of farms) {
    const rings = f.boundary.type === "Polygon" ? f.boundary.coordinates : f.boundary.coordinates.flat();
    for (const r of rings)
      for (const [x, y] of r) {
        minX = Math.min(minX, x); minY = Math.min(minY, y);
        maxX = Math.max(maxX, x); maxY = Math.max(maxY, y);
      }
  }
  return minX <= maxX ? [[minX, minY], [maxX, maxY]] : null;
}

/** Farms on imagery. Click one to open it. */
export function FarmMap({
  farms,
  className = "h-80",
  linkBase = "/app/farms",
}: {
  farms: MapFarm[];
  className?: string;
  linkBase?: string | null;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const router = useRouter();
  const [style, setStyle] = useState<"satellite" | "streets">("satellite");

  useEffect(() => {
    if (!el.current) return;
    const m = new maplibregl.Map({
      container: el.current,
      style: baseStyle("satellite"),
      center: [78, 15],
      zoom: 3,
      attributionControl: { compact: true },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const draw = () => {
      const data = {
        type: "FeatureCollection" as const,
        features: farms.map((f) => ({
          type: "Feature" as const,
          id: f.id,
          properties: { id: f.id, name: f.name, status: f.status, area: f.area_ha },
          geometry: f.boundary,
        })),
      };
      // A 2 ha field is a few pixels at district zoom, so farms are dots
      // until there is room to draw their boundaries.
      const points = {
        type: "FeatureCollection" as const,
        features: farms.map((f) => {
          const b = bounds([f])!;
          return {
            type: "Feature" as const,
            properties: { id: f.id, name: f.name, status: f.status, area: f.area_ha },
            geometry: { type: "Point" as const, coordinates: [(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2] },
          };
        }),
      };
      const src = m.getSource("farms") as GeoJSONSource | undefined;
      if (src) {
        src.setData(data);
        (m.getSource("farm-points") as GeoJSONSource).setData(points);
      } else {
        m.addSource("farms", { type: "geojson", data });
        m.addSource("farm-points", { type: "geojson", data: points });
        m.addLayer({ id: "farms-fill", type: "fill", source: "farms", minzoom: 12, paint: { "fill-color": STATUS_COLOR as never, "fill-opacity": 0.28 } });
        m.addLayer({ id: "farms-line", type: "line", source: "farms", minzoom: 12, paint: { "line-color": STATUS_COLOR as never, "line-width": 2 } });
        m.addLayer({
          id: "farms-dot",
          type: "circle",
          source: "farm-points",
          maxzoom: 12,
          paint: {
            "circle-color": STATUS_COLOR as never,
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 4, 11, 7],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1.5,
          },
        });
        const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });
        for (const layer of ["farms-fill", "farms-dot"]) {
          m.on("mousemove", layer, (e) => {
            m.getCanvas().style.cursor = linkBase ? "pointer" : "";
            const p = e.features?.[0]?.properties;
            if (p) popup.setLngLat(e.lngLat).setText(`${p.name} · ${Number(p.area).toFixed(2)} ha`).addTo(m);
          });
          m.on("mouseleave", layer, () => {
            m.getCanvas().style.cursor = "";
            popup.remove();
          });
          if (linkBase) {
            m.on("click", layer, (e) => {
              const id = e.features?.[0]?.properties?.id;
              if (id) router.push(`${linkBase}/${id}`);
            });
          }
        }
      }
      const b = bounds(farms);
      if (b) m.fitBounds(b, { padding: 40, maxZoom: 17, duration: 0 });
    };
    if (m.isStyleLoaded()) draw();
    else m.once("load", draw);
  }, [farms, linkBase, router]);

  useEffect(() => {
    const m = map.current;
    if (!m || !m.isStyleLoaded()) return;
    m.removeLayer("base");
    m.addLayer({ id: "base", type: "raster", source: style }, m.getLayer("farms-fill") ? "farms-fill" : undefined);
  }, [style]);

  return (
    <div className={`relative overflow-hidden rounded-xl border border-border ${className}`}>
      <div ref={el} className="h-full w-full" />
      <div className="absolute left-2 top-2 flex overflow-hidden rounded-lg border border-border bg-surface text-xs shadow">
        {(["satellite", "streets"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStyle(s)}
            className={`px-2.5 py-1 capitalize ${style === s ? "bg-brand text-white" : "text-muted hover:bg-surface-2"}`}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
