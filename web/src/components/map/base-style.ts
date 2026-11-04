import type { StyleSpecification } from "maplibre-gl";

// Imagery for drawing fields, OpenStreetMap for finding the village. Neither
// needs a key. Swap in a commercial basemap by changing these two sources.
export function baseStyle(kind: "satellite" | "streets" = "satellite"): StyleSpecification {
  return {
    version: 8,
    sources: {
      satellite: {
        type: "raster",
        tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
        tileSize: 256,
        maxzoom: 19,
        attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
      },
      streets: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        maxzoom: 19,
        attribution: "© OpenStreetMap contributors",
      },
    },
    layers: [{ id: "base", type: "raster", source: kind }],
  };
}
