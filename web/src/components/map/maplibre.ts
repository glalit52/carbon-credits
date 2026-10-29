import * as maplibregl from "maplibre-gl";

// See scripts/copy-maplibre-worker.mjs: the worker is served from /maplibre
// because the bundler moves MapLibre away from the file it would look for.
maplibregl.setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

export { maplibregl };
