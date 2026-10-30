import { zipSync } from "fflate";
import { NextResponse } from "next/server";

import {
  getOrgContext,
  getProject,
  getVintage,
  listAuditFor,
  listEstimateRows,
  listFarmers,
  listFarms,
  listPayments,
  listPractices,
  listRetirements,
  listSensorUploads,
  listSoil,
  memberNames,
  vintageClaims,
} from "@/lib/data";
import { DEMO } from "@/lib/env";
import { buildPack } from "@/lib/evidence-pack";
import { supabaseServer } from "@/lib/supabase/server";

// One zip per vintage, read with the downloader's own access: a member sees
// in the pack exactly what they could see on the pages.

const MAX_ATTACHMENT_BYTES = 40 * 1024 * 1024;

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ctx = await getOrgContext();
  const org = ctx.org.id;
  const found = await getVintage(org, id);
  if (!found) return new NextResponse("Not found", { status: 404 });
  const { vintage, events } = found;
  const project = await getProject(org, vintage.project_id);
  if (!project) return new NextResponse("Not found", { status: 404 });

  const farmIds = ((vintage.derivation as { farms?: { farm_id: string }[] })?.farms ?? []).map((f) => f.farm_id);
  const [farms, farmers, estimateRows, payments, retirements, claims, names, loggers] = await Promise.all([
    listFarms(org, { projectId: project.id }),
    listFarmers(org),
    listEstimateRows(org, farmIds),
    listPayments(org, vintage.id),
    listRetirements(org),
    vintageClaims(org),
    memberNames(org),
    listSensorUploads(org),
  ]);
  const inVintage = new Set(farmIds);
  const [practices, soil] = await Promise.all([
    Promise.all(farmIds.map((f) => listPractices(org, f))).then((r) => r.flat().filter((p) => p.year === vintage.year)),
    Promise.all(farmIds.map((f) => listSoil(org, f))).then((r) => r.flat()),
  ]);
  const audit = await listAuditFor(org, [vintage.id, ...payments.map((p) => p.id)]);

  // Evidence files behind the practice records, while the pack stays a sane size.
  const attachments = new Map<string, Uint8Array>();
  const missingAttachments: string[] = [];
  const paths = practices.map((p) => p.evidence_path).filter((p): p is string => !!p);
  if (!DEMO && paths.length) {
    const supabase = await supabaseServer();
    let total = 0;
    for (const path of paths) {
      const { data } = await supabase.storage.from("evidence").download(path);
      if (!data || total + data.size > MAX_ATTACHMENT_BYTES) {
        missingAttachments.push(path);
        continue;
      }
      total += data.size;
      attachments.set(path, new Uint8Array(await data.arrayBuffer()));
    }
  } else {
    missingAttachments.push(...paths);
  }

  const files = buildPack({
    generatedAt: new Date().toISOString(),
    generatedBy: ctx.user.name ?? ctx.user.email ?? ctx.user.id,
    organisation: ctx.org.name,
    project,
    vintage,
    events,
    farms: farms.filter((f) => inVintage.has(f.id)),
    farmers,
    estimateRows,
    practices,
    soil,
    loggers: loggers.filter((l) => inVintage.has(l.farm_id)),
    payments,
    retirements: retirements.filter((r) => r.vintage_id === vintage.id),
    claims: claims.get(vintage.id) ?? null,
    audit,
    names,
    attachments,
    missingAttachments,
  });
  const zip = zipSync(Object.fromEntries(files), { level: 6, mtime: new Date(vintage.updated_at) });
  const name = `${project.name}-${vintage.year}-evidence`.replace(/[^\w.-]+/g, "_");
  return new NextResponse(Buffer.from(zip), {
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="${name}.zip"`,
      "Cache-Control": "no-store",
    },
  });
}
