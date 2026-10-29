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
  totals: { creditable_net_t: number; potential_gross_t: number; potential_net_t: number };
  notes: string[];
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

export async function runForecast(body: Record<string, unknown>): Promise<ForecastResult> {
  const cfg = engineConfig();
  if (!cfg) {
    throw new EngineError(
      "The engine is not connected. Set CARBONSTACK_ENGINE_URL and CARBONSTACK_ENGINE_TOKEN (see web/README.md).",
    );
  }
  const res = await fetch(`${cfg.url}/api/forecast`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${cfg.token}` },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(60_000),
  }).catch((e: Error) => {
    throw new EngineError(`Could not reach the engine at ${cfg.url}: ${e.message}`);
  });
  const json = (await res.json().catch(() => ({}))) as { error?: string } & Partial<ForecastResult>;
  if (!res.ok) throw new EngineError(json.error ?? `engine returned HTTP ${res.status}`);
  return json as ForecastResult;
}
