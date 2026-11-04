import { NextResponse, type NextRequest } from "next/server";

import { toCsv } from "@/lib/csv";
import {
  getOrgContext,
  listEstimates,
  listFarmers,
  listFarms,
  listPayments,
  listProjects,
  listVintages,
} from "@/lib/data";
import type { EngineResult } from "@/lib/engine";

// Downloads for verifiers, buyers and spreadsheets. Each reads through the
// same functions as the pages, so an export holds exactly what the person
// downloading it is allowed to see.

function download(body: string, filename: string, type: string) {
  return new NextResponse(body, {
    headers: {
      "Content-Type": `${type}; charset=utf-8`,
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Cache-Control": "no-store",
    },
  });
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ kind: string }> }) {
  const { kind } = await params;
  const ctx = await getOrgContext();
  const org = ctx.org.id;
  const stamp = new Date().toISOString().slice(0, 10);
  const projectId = request.nextUrl.searchParams.get("project") ?? undefined;

  if (kind === "farms.csv" || kind === "farms.geojson") {
    const [farms, farmers, projects] = await Promise.all([
      listFarms(org, { projectId }),
      listFarmers(org),
      listProjects(org),
    ]);
    const farmer = new Map(farmers.map((f) => [f.id, f]));
    const project = new Map(projects.map((p) => [p.id, p.name]));
    if (kind === "farms.geojson") {
      const fc = {
        type: "FeatureCollection",
        features: farms.map((f) => ({
          type: "Feature",
          geometry: f.boundary,
          properties: {
            id: f.id, name: f.name, farm_ref: f.external_ref, area_ha: Number(f.area_ha),
            farmer: farmer.get(f.farmer_id ?? "")?.name ?? null, project: project.get(f.project_id ?? "") ?? null,
            status: f.status, tenure: f.tenure, enrolled_on: f.enrolled_on,
          },
        })),
      };
      return download(JSON.stringify(fc), `farms-${stamp}.geojson`, "application/geo+json");
    }
    return download(
      toCsv(
        ["farm_id", "farm_name", "farm_ref", "project", "farmer", "farmer_ref", "village", "area_ha",
         "centroid_lat", "centroid_lon", "crop", "practice", "tenure", "tenure_reference", "rice_ecosystem",
         "water_control", "enrolled_on", "status", "source"],
        farms.map((f) => {
          const fr = farmer.get(f.farmer_id ?? "");
          return [f.id, f.name, f.external_ref, project.get(f.project_id ?? ""), fr?.name, fr?.external_ref,
            fr?.village, Number(f.area_ha), f.centroid_lat, f.centroid_lon, f.crop, f.practice, f.tenure,
            f.tenure_reference, f.rice_ecosystem, f.water_control, f.enrolled_on, f.status, f.source];
        }),
      ),
      `farms-${stamp}.csv`,
      "text/csv",
    );
  }

  if (kind === "farmers.csv") {
    const farmers = await listFarmers(org);
    return download(
      toCsv(
        ["farmer_id", "name", "farmer_ref", "phone", "village", "district", "state", "country", "consent_on",
         "consent_reference", "carbon_rights_ref", "carbon_rights_signed_on", "payout_method"],
        farmers.map((f) => [f.id, f.name, f.external_ref, f.phone, f.village, f.district, f.state, f.country,
          f.consent_on, f.consent_reference, f.carbon_rights_ref, f.carbon_rights_signed_on, f.payout_method]),
      ),
      `farmers-${stamp}.csv`,
      "text/csv",
    );
  }

  if (kind === "estimates.csv") {
    const [estimates, farms] = await Promise.all([listEstimates(org), listFarms(org, { projectId })]);
    const farm = new Map(farms.map((f) => [f.id, f]));
    return download(
      toCsv(
        ["farm_id", "farm_name", "year", "methodology", "gross_t", "net_t", "potential_net_t", "data_quality",
         "blockers", "estimated_at"],
        estimates
          .filter((e) => farm.has(e.farm_id))
          .map((e) => {
            const r = e.result as unknown as EngineResult;
            return [e.farm_id, farm.get(e.farm_id)!.name, e.year, e.methodology, Number(e.gross_t), Number(e.net_t),
              r.vintages?.[0]?.potential?.net_t ?? null, e.data_quality, (r.blockers ?? []).join("; "), e.created_at];
          }),
      ),
      `estimates-${stamp}.csv`,
      "text/csv",
    );
  }

  if (kind === "payments.csv") {
    const [payments, farmers, vintages, projects] = await Promise.all([
      listPayments(org, request.nextUrl.searchParams.get("vintage") ?? undefined),
      listFarmers(org),
      listVintages(org),
      listProjects(org),
    ]);
    const farmer = new Map(farmers.map((f) => [f.id, f]));
    const vintage = new Map(vintages.map((v) => [v.id, v]));
    const project = new Map(projects.map((p) => [p.id, p.name]));
    return download(
      toCsv(
        ["payment_id", "farmer", "farmer_ref", "payout_method", "payout_reference", "project", "vintage_year",
         "credits", "amount", "currency", "status", "due_on", "paid_on", "reference"],
        payments.map((p) => {
          const f = farmer.get(p.farmer_id);
          const v = vintage.get(p.vintage_id);
          return [p.id, f?.name, f?.external_ref, f?.payout_method, f?.payout_reference,
            v ? project.get(v.project_id) : null, v?.year, Number(p.credits), Number(p.amount), p.currency,
            p.status, p.due_on, p.paid_on, p.reference];
        }),
      ),
      `payments-${stamp}.csv`,
      "text/csv",
    );
  }

  if (kind === "vintage.csv") {
    const id = request.nextUrl.searchParams.get("id");
    const vintages = await listVintages(org);
    const v = vintages.find((x) => x.id === id);
    if (!v) return NextResponse.json({ error: "Vintage not found." }, { status: 404 });
    const farms = await listFarms(org, { projectId: v.project_id });
    const name = new Map(farms.map((f) => [f.id, f]));
    const d = v.derivation as { farms?: { farm_id: string; gross_t: number; net_t: number; estimate_id?: string }[] };
    return download(
      toCsv(
        ["vintage_id", "year", "status", "farm_id", "farm_name", "farm_ref", "area_ha", "gross_t", "net_t",
         "share_of_net", "estimate_id"],
        (d.farms ?? []).map((f) => [v.id, v.year, v.status, f.farm_id, name.get(f.farm_id)?.name,
          name.get(f.farm_id)?.external_ref, name.get(f.farm_id)?.area_ha ?? null, f.gross_t, f.net_t,
          Number(v.net_t) ? f.net_t / Number(v.net_t) : 0, f.estimate_id]),
      ),
      `vintage-${v.year}-${stamp}.csv`,
      "text/csv",
    );
  }

  return NextResponse.json({ error: `unknown export "${kind}"` }, { status: 404 });
}
