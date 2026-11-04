"use server";

import { revalidatePath } from "next/cache";

import type { AuthorisedUse, RetirementPurpose } from "@/lib/database.types";
import { getOrgContext } from "@/lib/data";
import { can } from "@/lib/roles";
import { supabaseServer } from "@/lib/supabase/server";

import { type ActionResult, explain, num, refuseInDemo, str } from "./result";

const PURPOSES: RetirementPurpose[] = ["contribution", "offset", "corsia"];
const USES: AuthorisedUse[] = ["other_party_ndc", "corsia", "other_international_mitigation_purposes"];

/** Retire whole credits from an issued vintage. retire_credits() enforces
    the rules (enough left, an adjustment behind any offset); this only asks. */
export async function retireCredits(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.administer(ctx.role)) return { error: "Only owners and admins retire credits." };
  const vintage = str(form, "vintage_id");
  const credits = num(form, "credits");
  const beneficiary = str(form, "beneficiary");
  const purpose = str(form, "purpose") as RetirementPurpose | null;
  if (!vintage || !credits || !Number.isInteger(credits) || credits < 1) return { error: "Retire a whole number of credits." };
  if (!beneficiary) return { error: "Name who the credits are retired for." };
  if (!purpose || !PURPOSES.includes(purpose)) return { error: "Pick what the retirement is for." };
  const supabase = await supabaseServer();
  const { data, error } = await supabase.rpc("retire_credits", {
    vintage,
    credits,
    beneficiary_name: beneficiary,
    retire_purpose: purpose,
  });
  if (error) return { error: explain(error.message) };
  revalidatePath("/app/claims");
  return { message: `Retired serials ${data.serial_start}–${data.serial_end} for ${data.beneficiary}.`, id: data.id };
}

export async function addAuthorisation(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.administer(ctx.role)) return { error: "Only owners and admins record authorisations." };
  const project_id = str(form, "project_id");
  const authority = str(form, "authority");
  const reference = str(form, "reference");
  const issued_on = str(form, "issued_on");
  const use = str(form, "authorised_use") as AuthorisedUse | null;
  const volume = num(form, "authorised_volume_t");
  const first = num(form, "first_vintage");
  const last = num(form, "last_vintage");
  if (!project_id || !authority || !reference || !issued_on || !use || !volume || !first || !last) {
    return { error: "Every field except the expiry date is required." };
  }
  if (!USES.includes(use)) return { error: "Unknown authorised use." };
  if (last < first) return { error: "The last vintage cannot be before the first." };
  const supabase = await supabaseServer();
  const { error } = await supabase.from("authorisations").insert({
    org_id: ctx.org.id,
    project_id,
    authority,
    reference,
    issued_on,
    authorised_use: use,
    authorised_volume_t: volume,
    adjustment_committed: str(form, "adjustment_committed") === "yes",
    first_vintage: first,
    last_vintage: last,
    valid_until: str(form, "valid_until"),
    created_by: ctx.user.id,
  });
  if (error) return { error: explain(error.message) };
  revalidatePath("/app/claims");
  return { message: "Authorisation recorded. It changes nothing a buyer may claim until an adjustment is reported against it." };
}

export async function addAdjustment(_: ActionResult, form: FormData): Promise<ActionResult> {
  const refused = refuseInDemo();
  if (refused) return refused;
  const ctx = await getOrgContext();
  if (!can.administer(ctx.role)) return { error: "Only owners and admins record adjustments." };
  const authorisation_id = str(form, "authorisation_id");
  const year = num(form, "vintage_year");
  const volume = num(form, "volume_t");
  const reported_on = str(form, "reported_on");
  const reference = str(form, "reference");
  if (!authorisation_id || !year || !volume || !reported_on || !reference) {
    return { error: "Every field is required: an adjustment without its report reference is not evidence." };
  }
  const supabase = await supabaseServer();
  const { error } = await supabase.from("adjustments").insert({
    org_id: ctx.org.id,
    authorisation_id,
    vintage_year: year,
    volume_t: volume,
    reported_on,
    reference,
    created_by: ctx.user.id,
  });
  if (error) return { error: explain(error.message) };
  revalidatePath("/app/claims");
  return { message: "Adjustment recorded." };
}
