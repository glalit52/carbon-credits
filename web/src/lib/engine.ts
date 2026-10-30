import "server-only";

import type { Farm, Farmer, Pathway } from "@/lib/database.types";
import { engineConfig } from "@/lib/env";

// Calls the Python engine's POST /api/estimate (api/index.py). The engine is
// stateless; what comes back is stored by the caller as estimate rows.

export type EngineVintage = {
  year: number;
  skipped?: string;
  gross_t?: number;
  net_t?: number;
  area_ha?: number;
  relative_uncertainty?: number;
  deductions?: { name: string; fraction: number; basis: string; amount_t: number }[];
  warnings?: string[];
  calculations?: { label?: string; result?: number; [k: string]: unknown }[];
  potential?: { gross_t: number; net_t: number; relative_uncertainty: number };
};

export type EngineResult = {
  methodology: string;
  pathway: string;
  data_quality: string;
  blockers: string[];
  site: {
    centroid: { lat: number; lon: number };
    area_ha: number;
    climate: { source: string; quality: string; monthly_rain_mm: number[]; mean_temp_c: number };
    assumptions: { parameter: string; value: unknown; basis: string }[];
  };
  vintages: EngineVintage[];
  seasons: Record<string, unknown>[];
  monitoring?: Monitoring;
  totals: { creditable_net_t: number; potential_gross_t: number; potential_net_t: number };
  notes: string[];
};

// ---------------------------------------------------------------------------
// Monitoring: the series an estimate was built from (estimate.py _monitoring)
// ---------------------------------------------------------------------------

export type WaterState = "flooded" | "drained" | "ambiguous";

export type RadarCall = {
  day: string;
  state: WaterState;
  p_flooded: number;
  confidence: number;
  stage_estimate: number;
  separation_db: number;
  vv_db: number;
  vh_db: number;
  inferred: boolean;
  mixed_orbit: boolean;
  note: string;
  season: string;
};

export type DrySpell = {
  start: string;
  end: string;
  days: number;
  passes: number;
  mean_confidence: number;
  spanned_ambiguous: number;
  terminal: boolean;
};

export type Regime = {
  season: string;
  year: number;
  start: string;
  end: string;
  passes: number;
  usable_passes: number;
  flooded_passes: number;
  drained_passes: number;
  ambiguous_passes: number;
  coverage: number;
  drained_fraction: number;
  spells: DrySpell[];
  qualifying_spells: number;
  adoption_confidence: number;
  warnings: string[];
};

export type OpticalReading = {
  day: string;
  ndvi: number | null;
  rain_mm: number;
  season: string;
  water?: number;
  canopy_m?: number;
  canopy_sd_m?: number;
};

export type Monitoring = {
  simulated: boolean;
  years: number[];
  optical: OpticalReading[];
  radar: RadarCall[];
  regimes: Regime[];
};

// POST /api/sensors (monitoring_api.sensors_request)
export type LoggerResult = {
  readings: number;
  other_plots: string[];
  records: {
    device_id: string;
    plot_id: string;
    days: number;
    clear_days: number;
    dropped_spikes: number;
    flatline_hours: number;
    gap_days: string[];
    dry_downs: { from: string; to: string; deepest_cm: number }[];
    issues: string[];
  }[];
  days: { device_id: string; day: string; mean_cm: number; min_cm: number; state: WaterState }[];
  thresholds: { flooded_above_cm: number; drained_below_cm: number; safe_awd_cm: number };
  validation: {
    plot_id: string;
    devices: string[];
    matched_passes: number;
    unmatched_passes: number;
    sufficient: boolean;
    over_credit_errors: number;
    called: number;
    abstained: number;
    accuracy: number;
    precision_flooded: number;
    recall_flooded: number;
    drained_accuracy: number;
    true_positive: number;
    false_positive: number;
    true_negative: number;
    false_negative: number;
  } | null;
};

// POST /api/scenes (monitoring_api.scenes_request)
export type SceneCoverage = {
  collection: string;
  start: string;
  end: string;
  scenes: number;
  acquisition_days: number;
  usable_days: number;
  max_cloud: number | null;
  median_revisit_days: number | null;
  max_gap_days: number;
  platforms: string[];
  scene_list: {
    id: string;
    day: string;
    platform: string;
    cloud_cover: number | null;
    relative_orbit: number | null;
    orbit_state: string | null;
    usable: boolean;
  }[];
};

// POST /api/reconcile (monitoring_api.reconcile_request)
export type Reconciliation = {
  registry: string;
  clean: boolean;
  matched: number;
  disagreements: number;
  missing_at_registry: string[];
  unknown_to_us: number[];
  retired_t: number;
  cancelled_t: number;
  findings: string[];
  columns: Record<string, string>;
  ignored_columns: string[];
  rows: number;
  matches: { issuance_id: string; registry_line: number; basis: string; ours: number; theirs: number; agrees: boolean }[];
  unknown_rows: { line: number; vintage: number | null; quantity: number; serial: string; status: string }[];
};

export class EngineError extends Error {}

export function estimateRequest(farm: Farm, farmer: Farmer | null, pathway: Pathway, years?: number[]) {
  if (pathway !== "rice" && pathway !== "agroforestry") {
    throw new EngineError(`the engine estimates rice and agroforestry farms; this project is "${pathway}"`);
  }
  return {
    farm: {
      id: farm.external_ref ?? farm.id.slice(0, 8),
      name: farm.name,
      pathway,
      boundary: farm.boundary,
      enrolled_on: farm.enrolled_on,
      seasons: farm.seasons?.length ? farm.seasons : null,
      crop: farm.crop,
      practice: farm.practice,
      tenure: farm.tenure ?? "undocumented",
      tenure_reference: farm.tenure_reference,
      rice_ecosystem: farm.rice_ecosystem,
      water_control: farm.water_control,
      species: farm.species,
      farmer_name: farmer?.name,
      village: farmer?.village,
      country: farmer?.country,
      region: farmer?.district,
    },
    ...(years ? { years } : {}),
    climate_source: "auto",
  };
}

export async function runEstimate(request: ReturnType<typeof estimateRequest>): Promise<EngineResult> {
  const cfg = engineConfig();
  if (!cfg) {
    throw new EngineError(
      "The estimate engine is not connected. Set CARBONSTACK_ENGINE_URL and CARBONSTACK_ENGINE_TOKEN (see web/README.md).",
    );
  }
  let res: Response;
  try {
    res = await fetch(`${cfg.url}/api/estimate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${cfg.token}` },
      body: JSON.stringify(request),
      cache: "no-store",
      signal: AbortSignal.timeout(60_000),
    });
  } catch (e) {
    throw new EngineError(`Could not reach the engine at ${cfg.url}: ${(e as Error).message}`);
  }
  const body = (await res.json().catch(() => ({}))) as { error?: string } & Partial<EngineResult>;
  if (!res.ok) throw new EngineError(body.error ?? `engine returned HTTP ${res.status}`);
  return body as EngineResult;
}

// ---------------------------------------------------------------------------
// POST /api/forecast (src/carbonstack/forecast_api.py)
// ---------------------------------------------------------------------------

export type YearForecast = {
  year: number;
  projected_t: number;
  p10: number;
  p50: number;
  p90: number;
  mean: number;
  safe_t: number;
  confidence: number;
  haircut: number;
  zero_rate: number;
};

export type ForecastResult = {
  forecast: {
    trials: number;
    confidence: number;
    projected_total_t: number;
    p50_total_t: number;
    safe_total_t: number;
    portfolio_haircut: number;
    years: YearForecast[];
    sensitivity: Record<string, number>;
    dominant_risk: { risk: string; safe_volume_cost_t: number } | null;
    warnings: string[];
    risk_source: string;
  };
  risk: {
    dropout_per_year: number;
    practice_lapse_per_year: number;
    planting_failure_per_year: number;
    verification_slip_per_year: number;
    enrolled_units: number;
    source: string;
  };
  aggregation: { units: number; safe_t: number; p50_t: number; haircut: number }[];
  offtake: {
    committed_t: number;
    delivery_probability: number;
    expected_shortfall_t: number;
    worst_case_shortfall_t: number;
    replacement_price: number;
    expected_cover_cost: number;
    verdict: string;
  } | null;
};

export function runForecast(body: Record<string, unknown>): Promise<ForecastResult> {
  return callEngine<ForecastResult>("/api/forecast", body);
}

export function runSensors(body: { csv: string; plot_id?: string; radar?: RadarCall[] }): Promise<LoggerResult> {
  return callEngine<LoggerResult>("/api/sensors", body);
}

export function runScenes(body: { boundary: unknown; start: string; end: string; sensor: "s1" | "s2" }) {
  return callEngine<SceneCoverage>("/api/scenes", body);
}

export function runReconcile(body: {
  registry: string;
  csv: string;
  issuances: { id: string; year: number; quantity: number; registry_ref: string | null; issued_on?: string }[];
}): Promise<Reconciliation> {
  return callEngine<Reconciliation>("/api/reconcile", body);
}

/** POST to one of the engine's stateless routes; its 422 message comes back as an EngineError. */
async function callEngine<T>(path: string, body: unknown): Promise<T> {
  const cfg = engineConfig();
  if (!cfg) {
    throw new EngineError(
      "The engine is not connected. Set CARBONSTACK_ENGINE_URL and CARBONSTACK_ENGINE_TOKEN (see web/README.md).",
    );
  }
  const res = await fetch(`${cfg.url}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${cfg.token}` },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(60_000),
  }).catch((e: Error) => {
    throw new EngineError(`Could not reach the engine at ${cfg.url}: ${e.message}`);
  });
  const json = (await res.json().catch(() => ({}))) as { error?: string };
  if (!res.ok) throw new EngineError(json.error ?? `engine returned HTTP ${res.status}`);
  return json as T;
}
