import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { cache } from "react";

import type {
  AuditEvent,
  Estimate,
  Farm,
  Farmer,
  ImportRun,
  Integration,
  Invitation,
  Organization,
  Payment,
  PracticeRecord,
  Project,
  Role,
  SoilSample,
  Vintage,
  VintageEvent,
} from "@/lib/database.types";
import { demo } from "@/lib/demo";
import { DEMO } from "@/lib/env";
import { supabaseServer } from "@/lib/supabase/server";

// Every read the pages make, in one place. In demo mode it serves the
// engine-built sample organisation; otherwise it asks Supabase as the signed-
// in user, so row-level security decides what comes back. Nothing here filters
// by organisation for safety -- the database does that -- the org filter is
// only so a user in two organisations sees the one they are working in.

export const ACTIVE_ORG_COOKIE = "active_org";

export type SessionUser = { id: string; email: string | null; name: string | null };
export type OrgContext = {
  user: SessionUser;
  org: Organization;
  role: Role;
  orgs: { org: Organization; role: Role }[];
  demo: boolean;
};

export const getUser = cache(async (): Promise<SessionUser | null> => {
  // Per-request, always: a page about one user's organisation must never be
  // prerendered and served to another, whatever the build-time settings were.
  await connection();
  if (DEMO) {
    const m = demo.members.find((x) => x.user_id === demo.viewer)!;
    return { id: m.user_id, email: m.email, name: m.full_name };
  }
  const supabase = await supabaseServer();
  const { data } = await supabase.auth.getUser();
  if (!data.user) return null;
  return {
    id: data.user.id,
    email: data.user.email ?? null,
    name: (data.user.user_metadata?.full_name as string | undefined) ?? null,
  };
});

/** The user, their organisations and the one they are working in. */
export const getOrgContext = cache(async (): Promise<OrgContext> => {
  const user = await getUser();
  if (!user) redirect("/login");
  if (DEMO) {
    return {
      user,
      org: demo.organization,
      role: "owner",
      orgs: [{ org: demo.organization, role: "owner" }],
      demo: true,
    };
  }
  const supabase = await supabaseServer();
  const { data: memberships, error } = await supabase
    .from("memberships")
    .select("org_id, role")
    .eq("user_id", user.id);
  if (error) throw new Error(`could not load memberships: ${error.message}`);
  if (!memberships?.length) redirect("/onboarding");
  const { data: orgRows } = await supabase
    .from("organizations")
    .select("*")
    .in("id", memberships.map((m) => m.org_id));
  const orgs = (orgRows ?? []).map((org) => ({
    org,
    role: memberships.find((m) => m.org_id === org.id)!.role,
  }));
  if (!orgs.length) redirect("/onboarding");
  const wanted = (await cookies()).get(ACTIVE_ORG_COOKIE)?.value;
  const active = orgs.find((o) => o.org.id === wanted) ?? orgs[0];
  return { user, org: active.org, role: active.role, orgs, demo: false };
});

async function q<T>(
  build: (s: Awaited<ReturnType<typeof supabaseServer>>) => PromiseLike<{ data: T | null; error: { message: string } | null }>,
): Promise<T> {
  const supabase = await supabaseServer();
  const { data, error } = await build(supabase);
  if (error) throw new Error(error.message);
  return (data ?? []) as T;
}

// ---------------------------------------------------------------------------

export async function listProjects(orgId: string): Promise<Project[]> {
  if (DEMO) return demo.projects;
  return q((s) => s.from("projects").select("*").eq("org_id", orgId).order("created_at"));
}

export async function getProject(orgId: string, id: string): Promise<Project | null> {
  return (await listProjects(orgId)).find((p) => p.id === id) ?? null;
}

export async function listFarms(
  orgId: string,
  filter: { projectId?: string; farmerId?: string } = {},
): Promise<Farm[]> {
  if (DEMO) {
    return demo.farms.filter(
      (f) =>
        (!filter.projectId || f.project_id === filter.projectId) &&
        (!filter.farmerId || f.farmer_id === filter.farmerId),
    );
  }
  return q((s) => {
    let query = s.from("farms").select("*").eq("org_id", orgId);
    if (filter.projectId) query = query.eq("project_id", filter.projectId);
    if (filter.farmerId) query = query.eq("farmer_id", filter.farmerId);
    return query.order("created_at", { ascending: false });
  });
}

export async function getFarm(orgId: string, id: string): Promise<Farm | null> {
  if (DEMO) return demo.farms.find((f) => f.id === id) ?? null;
  const supabase = await supabaseServer();
  const { data } = await supabase.from("farms").select("*").eq("org_id", orgId).eq("id", id).maybeSingle();
  return data;
}

export async function listFarmers(orgId: string): Promise<Farmer[]> {
  if (DEMO) return demo.farmers;
  return q((s) => s.from("farmers").select("*").eq("org_id", orgId).order("name"));
}

export async function getFarmer(orgId: string, id: string): Promise<Farmer | null> {
  if (DEMO) return demo.farmers.find((f) => f.id === id) ?? null;
  const supabase = await supabaseServer();
  const { data } = await supabase.from("farmers").select("*").eq("org_id", orgId).eq("id", id).maybeSingle();
  return data;
}

/** Latest estimate per farm and year. */
export async function listEstimates(orgId: string, farmId?: string): Promise<Estimate[]> {
  const rows: Estimate[] = DEMO
    ? demo.estimates.filter((e) => !farmId || e.farm_id === farmId)
    : await q((s) => {
        let query = s.from("estimates").select("*").eq("org_id", orgId);
        if (farmId) query = query.eq("farm_id", farmId);
        return query.order("created_at", { ascending: false }).limit(5000);
      });
  const latest = new Map<string, Estimate>();
  for (const e of rows) {
    const key = `${e.farm_id}:${e.year}`;
    const seen = latest.get(key);
    if (!seen || seen.created_at < e.created_at) latest.set(key, e);
  }
  return [...latest.values()].sort((a, b) => a.year - b.year);
}

export async function listPractices(orgId: string, farmId: string): Promise<PracticeRecord[]> {
  if (DEMO) return demo.practices.filter((p) => p.farm_id === farmId);
  return q((s) =>
    s.from("practice_records").select("*").eq("org_id", orgId).eq("farm_id", farmId).order("year"),
  );
}

export async function listSoil(orgId: string, farmId: string): Promise<SoilSample[]> {
  if (DEMO) return demo.soil.filter((p) => p.farm_id === farmId);
  return q((s) =>
    s.from("soil_samples").select("*").eq("org_id", orgId).eq("farm_id", farmId).order("sampled_on"),
  );
}

export async function listVintages(orgId: string, projectId?: string): Promise<Vintage[]> {
  if (DEMO) return demo.vintages.filter((v) => !projectId || v.project_id === projectId);
  return q((s) => {
    let query = s.from("vintages").select("*").eq("org_id", orgId);
    if (projectId) query = query.eq("project_id", projectId);
    return query.order("year", { ascending: false });
  });
}

export async function getVintage(
  orgId: string,
  id: string,
): Promise<{ vintage: Vintage; events: VintageEvent[] } | null> {
  if (DEMO) {
    const vintage = demo.vintages.find((v) => v.id === id);
    return vintage
      ? { vintage, events: demo.vintage_events.filter((e) => e.vintage_id === id) }
      : null;
  }
  const supabase = await supabaseServer();
  const { data: vintage } = await supabase
    .from("vintages")
    .select("*")
    .eq("org_id", orgId)
    .eq("id", id)
    .maybeSingle();
  if (!vintage) return null;
  const { data: events } = await supabase
    .from("vintage_events")
    .select("*")
    .eq("vintage_id", id)
    .order("at");
  return { vintage, events: events ?? [] };
}

export async function listPayments(orgId: string, vintageId?: string): Promise<Payment[]> {
  if (DEMO) return demo.payments.filter((p) => !vintageId || p.vintage_id === vintageId);
  return q((s) => {
    let query = s.from("payments").select("*").eq("org_id", orgId);
    if (vintageId) query = query.eq("vintage_id", vintageId);
    return query.order("created_at", { ascending: false });
  });
}

export async function listIntegrations(orgId: string): Promise<Integration[]> {
  if (DEMO) return demo.integrations;
  return q((s) => s.from("integrations").select("*").eq("org_id", orgId));
}

export type Member = { user_id: string; role: Role; full_name: string | null; created_at: string };

export async function listMembers(orgId: string): Promise<Member[]> {
  if (DEMO) return demo.members;
  const supabase = await supabaseServer();
  const { data: rows } = await supabase.from("memberships").select("*").eq("org_id", orgId);
  const ids = (rows ?? []).map((r) => r.user_id);
  const { data: profiles } = ids.length
    ? await supabase.from("profiles").select("id, full_name").in("id", ids)
    : { data: [] };
  return (rows ?? []).map((r) => ({
    user_id: r.user_id,
    role: r.role,
    created_at: r.created_at,
    full_name: profiles?.find((p) => p.id === r.user_id)?.full_name ?? null,
  }));
}

export async function listInvitations(orgId: string): Promise<Invitation[]> {
  if (DEMO) return demo.invitations;
  return q((s) =>
    s.from("invitations").select("*").eq("org_id", orgId).is("accepted_at", null).order("created_at"),
  );
}

export async function listAudit(orgId: string, limit = 100): Promise<AuditEvent[]> {
  if (DEMO) return demo.audit.slice(0, limit);
  return q((s) =>
    s.from("audit_events").select("*").eq("org_id", orgId).order("at", { ascending: false }).limit(limit),
  );
}

export async function listImports(orgId: string): Promise<ImportRun[]> {
  if (DEMO) return [];
  return q((s) =>
    s.from("imports").select("*").eq("org_id", orgId).order("created_at", { ascending: false }).limit(20),
  );
}

/** Names for user ids, for "who did this" columns. */
export async function memberNames(orgId: string): Promise<Map<string, string>> {
  const members = await listMembers(orgId);
  return new Map(members.map((m) => [m.user_id, m.full_name ?? "Member"]));
}

export const DEMO_AS_OF = demo.as_of;
