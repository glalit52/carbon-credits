// A vintage's verification pack: everything a verifier needs to re-derive the
// number, in files they can open without an account. Mirrors the layout of the
// engine's own pack (src/carbonstack/evidence.py) where the web app has the
// same records: a plot register, per-farm calculations, observations, the
// review trail and a manifest of hashes.
//
// Pure: takes records, returns files. The route fetches and zips.

import { createHash } from "node:crypto";

import { toCsv } from "@/lib/csv";
import type {
  AuditEvent,
  ClaimBasis,
  Estimate,
  Farm,
  Farmer,
  Payment,
  PracticeRecord,
  Project,
  Retirement,
  SensorUpload,
  SoilSample,
  Vintage,
  VintageEvent,
} from "@/lib/database.types";
import type { EngineResult, Monitoring } from "@/lib/engine";

export type PackInput = {
  generatedAt: string;
  generatedBy: string;
  organisation: string;
  project: Project;
  vintage: Vintage;
  events: VintageEvent[];
  farms: Farm[];
  farmers: Farmer[];
  /** Every stored row for the vintage's farms; the pack picks the ones the vintage names. */
  estimateRows: Estimate[];
  practices: PracticeRecord[];
  soil: SoilSample[];
  loggers: SensorUpload[];
  payments: Payment[];
  retirements: Retirement[];
  claims: ClaimBasis | null;
  audit: AuditEvent[];
  names: Map<string, string>;
  /** Evidence files fetched from storage, by their storage path. */
  attachments: Map<string, Uint8Array>;
  missingAttachments: string[];
};

type Derivation = {
  method?: string;
  built_at?: string;
  farms?: { farm_id: string; estimate_id: string; net_t: number; gross_t: number; data_quality?: string }[];
  excluded?: { farm_id: string; status: string }[];
};

const enc = new TextEncoder();
const sha256 = (b: Uint8Array) => createHash("sha256").update(b).digest("hex");
const slug = (s: string) => s.replace(/[^\w.-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 60) || "farm";

export function boundaryHash(boundary: unknown): string {
  return sha256(enc.encode(JSON.stringify(boundary))).slice(0, 16);
}

export function buildPack(input: PackInput): Map<string, Uint8Array> {
  const { vintage: v, project } = input;
  const files = new Map<string, Uint8Array>();
  const put = (path: string, body: string | Uint8Array) =>
    files.set(path, typeof body === "string" ? enc.encode(body) : body);
  const who = (id: string | null) => (id ? (input.names.get(id) ?? id.slice(0, 8)) : "");

  const d = (v.derivation ?? {}) as Derivation;
  const used = d.farms ?? [];
  const estimateById = new Map(input.estimateRows.map((e) => [e.id, e]));
  const farmById = new Map(input.farms.map((f) => [f.id, f]));
  const farmerById = new Map(input.farmers.map((f) => [f.id, f]));
  const missingEstimates = used.filter((u) => !estimateById.has(u.estimate_id)).map((u) => u.estimate_id);

  // -- plot register --------------------------------------------------------
  const register = used.map((u) => {
    const farm = farmById.get(u.farm_id);
    const farmer = farmerById.get(farm?.farmer_id ?? "");
    const est = estimateById.get(u.estimate_id);
    const result = est?.result as unknown as EngineResult | undefined;
    return [
      farm?.external_ref ?? u.farm_id, farm?.name, farmer?.external_ref, farmer?.name, farmer?.village,
      farm ? Number(farm.area_ha) : null, farm?.centroid_lat, farm?.centroid_lon,
      farm ? boundaryHash(farm.boundary) : null, farm?.tenure, farm?.tenure_reference,
      farmer?.consent_on, farmer?.consent_reference, farmer?.carbon_rights_ref, farm?.rice_ecosystem,
      farm?.water_control, farm?.enrolled_on, farm?.practice, u.estimate_id, est?.created_at, u.gross_t, u.net_t,
      u.data_quality ?? est?.data_quality, (result?.blockers ?? []).join("; "),
    ];
  });
  put(
    "plot_register.csv",
    toCsv(
      ["farm_ref", "farm", "farmer_ref", "farmer", "village", "area_ha", "centroid_lat", "centroid_lon",
       "boundary_sha256_16", "tenure", "tenure_reference", "consent_on", "consent_reference",
       "carbon_rights_reference", "rice_ecosystem", "water_control", "enrolled_on", "practice",
       "estimate_id", "estimated_at", "gross_t", "net_t", "data_quality", "blockers"],
      register,
    ),
  );
  put(
    "boundaries.geojson",
    JSON.stringify({
      type: "FeatureCollection",
      features: used.flatMap((u) => {
        const f = farmById.get(u.farm_id);
        return f
          ? [{ type: "Feature", geometry: f.boundary,
               properties: { farm_ref: f.external_ref, name: f.name, area_ha: Number(f.area_ha), net_t: u.net_t } }]
          : [];
      }),
    }, null, 1),
  );

  // -- calculations, one file per farm ------------------------------------------
  const radarRows: (string | number | boolean | null)[][] = [];
  const regimeRows: (string | number | null)[][] = [];
  for (const u of used) {
    const est = estimateById.get(u.estimate_id);
    if (!est) continue;
    const farm = farmById.get(u.farm_id);
    const ref = slug(farm?.external_ref ?? farm?.name ?? u.farm_id);
    put(`calculations/${ref}.json`, JSON.stringify({ estimate_id: est.id, created_at: est.created_at,
      engine_version: est.engine_version, input: est.input, result: est.result }, null, 1));

    // The run's monitoring series sits on its latest year's row.
    const run = input.estimateRows.filter((e) => e.farm_id === est.farm_id && e.created_at === est.created_at);
    const monitoring = run.map((e) => (e.result as unknown as EngineResult).monitoring).find(Boolean) as Monitoring | undefined;
    for (const c of monitoring?.radar ?? []) {
      if (!c.day.startsWith(String(v.year)) && !c.day.startsWith(String(v.year + 1))) continue;
      radarRows.push([farm?.external_ref ?? u.farm_id, c.day, c.season, c.vv_db, c.vh_db, c.state,
        c.p_flooded, c.confidence, c.inferred, c.note]);
    }
    for (const r of monitoring?.regimes ?? []) {
      if (r.year !== v.year) continue;
      regimeRows.push([farm?.external_ref ?? u.farm_id, r.season, r.year, r.passes, r.usable_passes,
        r.qualifying_spells, r.adoption_confidence, r.warnings.join("; ")]);
    }
  }
  if (radarRows.length) {
    put("observations/radar_passes.csv", toCsv(
      ["farm_ref", "day", "season", "vv_db_normalised", "vh_db_normalised", "call", "p_flooded", "confidence",
       "inferred", "note"], radarRows));
    put("observations/water_regimes.csv", toCsv(
      ["farm_ref", "season", "year", "passes", "readable_passes", "awd_events", "adoption_confidence", "warnings"],
      regimeRows));
  }
  for (const l of input.loggers) {
    const farm = farmById.get(l.farm_id);
    put(`observations/loggers/${slug(farm?.external_ref ?? l.farm_id)}-${slug(l.file_name)}.json`,
      JSON.stringify({ file_name: l.file_name, uploaded_at: l.created_at, uploaded_by: who(l.uploaded_by),
        stored_at: l.file_path, summary: l.summary }, null, 1));
  }

  // -- field records --------------------------------------------------------------
  const ref = (farmId: string) => farmById.get(farmId)?.external_ref ?? farmId;
  put("field/practice_records.csv", toCsv(
    ["farm_ref", "year", "season", "practice", "started_on", "ended_on", "notes", "evidence", "recorded_by", "recorded_at"],
    input.practices.map((p) => [ref(p.farm_id), p.year, p.season, p.practice, p.started_on, p.ended_on, p.notes,
      p.evidence_path ? `evidence/${slug(p.evidence_path.split("/").pop() ?? "file")}` : null,
      who(p.recorded_by), p.created_at])));
  put("field/soil_samples.csv", toCsv(
    ["farm_ref", "sampled_on", "depth_top_cm", "depth_bottom_cm", "soc_pct", "bulk_density", "lab", "lab_reference"],
    input.soil.map((s) => [ref(s.farm_id), s.sampled_on, s.depth_top_cm, s.depth_bottom_cm, s.soc_pct,
      s.bulk_density, s.lab, s.lab_reference])));
  for (const [path, body] of input.attachments) {
    put(`evidence/${slug(path.split("/").pop() ?? "file")}`, body);
  }

  // -- review, issuance and what happened to the credits ------------------------------
  put("review/vintage.json", JSON.stringify({ ...v, derivation: d }, null, 1));
  put("review/events.csv", toCsv(["at", "from", "to", "by", "note"],
    input.events.map((e) => [e.at, e.from_status, e.to_status, who(e.actor), e.note])));
  put("review/audit_log.csv", toCsv(["at", "action", "entity", "entity_id", "by", "detail"],
    input.audit.map((a) => [a.at, a.action, a.entity, a.entity_id, who(a.actor), a.detail ? JSON.stringify(a.detail) : null])));
  put("credits/farmer_payments.csv", toCsv(
    ["farmer_ref", "farmer", "credits", "amount", "currency", "status", "due_on", "paid_on", "reference"],
    input.payments.map((p) => {
      const f = farmerById.get(p.farmer_id);
      return [f?.external_ref, f?.name, Number(p.credits), Number(p.amount), p.currency, p.status, p.due_on,
        p.paid_on, p.reference];
    })));
  put("credits/retirements.csv", toCsv(
    ["id", "serial_start", "serial_end", "quantity", "beneficiary", "purpose", "claim", "retired_at"],
    input.retirements.map((r) => [r.id, r.serial_start, r.serial_end, r.quantity, r.beneficiary, r.purpose, r.claim,
      r.retired_at])));
  if (input.claims) put("credits/claim_basis.json", JSON.stringify(input.claims, null, 1));

  // -- summary and manifest, last, so the manifest covers everything above ------------
  const simulated = used.some((u) =>
    /simulated/i.test(u.data_quality ?? estimateById.get(u.estimate_id)?.data_quality ?? ""),
  );
  put("README.md", summary(input, d, used.length, missingEstimates, simulated, radarRows.length > 0));
  const manifest = {
    generated_at: input.generatedAt,
    generated_by: input.generatedBy,
    organisation: input.organisation,
    project: project.name,
    vintage: { id: v.id, year: v.year, status: v.status, net_t: Number(v.net_t), issuable: v.issuable },
    missing_estimates: missingEstimates,
    missing_attachments: input.missingAttachments,
    files: [...files.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([path, body]) => ({ path, bytes: body.length, sha256: sha256(body) })),
  };
  put("manifest.json", JSON.stringify(manifest, null, 1));
  return files;
}

function summary(
  input: PackInput,
  d: Derivation,
  farms: number,
  missing: string[],
  simulated: boolean,
  radar: boolean,
): string {
  const { vintage: v, project } = input;
  const lines = [
    `# ${project.name} — vintage ${v.year}`,
    "",
    `${input.organisation}. Generated ${input.generatedAt} by ${input.generatedBy}.`,
    "",
    "| | |",
    "|---|---|",
    `| Methodology | ${project.methodology}${project.registry ? ` (${project.registry})` : ""} |`,
    `| Status | ${v.status} |`,
    `| Gross | ${Number(v.gross_t).toFixed(4)} t CO2e |`,
    `| Net | ${Number(v.net_t).toFixed(4)} t CO2e |`,
    `| Whole credits | ${v.issuable} |`,
    `| Serials | ${v.serial_start != null ? `${v.serial_start}–${v.serial_end}` : "not issued"} |`,
    `| Registry reference | ${v.registry_ref ?? "not recorded"} |`,
    `| Farms | ${farms} |`,
    "",
    "## How the number is made",
    "",
    d.method ?? "Sum of farm estimates.",
    "",
    "Each farm's estimate is in `calculations/<farm>.json` with the exact request the engine was given and",
    "everything it returned: every parameter, deduction and citation. `plot_register.csv` lists the farms",
    "with their tenure, consent and carbon-rights references and a hash of each boundary, which is in",
    "`boundaries.geojson`.",
    "",
  ];
  if (simulated) {
    lines.push(
      "## Read this first",
      "",
      "Monitoring for these estimates is **simulated** from each farm's own climate and crop calendar.",
      ...(radar
        ? ["The radar calls in `observations/` come from the detector real Sentinel-1 data will go through, applied",
           "to simulated backscatter."]
        : []),
      "The series show how the estimate was made; they are not satellite measurements.",
      "",
    );
  }
  if (missing.length) {
    lines.push("## Missing", "", `${missing.length} estimate(s) the vintage names are no longer readable: ${missing.join(", ")}.`, "");
  }
  if (input.missingAttachments.length) {
    lines.push(`${input.missingAttachments.length} evidence file(s) could not be fetched; see manifest.json.`, "");
  }
  lines.push(
    "## Files",
    "",
    "- `plot_register.csv`, `boundaries.geojson`: the farms",
    "- `calculations/`: one engine record per farm",
    "- `observations/`: radar passes, water regimes, field-logger summaries",
    "- `field/`, `evidence/`: practice records, soil samples and the files behind them",
    "- `review/`: the vintage, its review trail and the audit log",
    "- `credits/`: farmer payments, retirements and the claim basis",
    "- `manifest.json`: SHA-256 of every file",
    "",
  );
  return lines.join("\n");
}
