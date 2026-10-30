import type { Farmer, Project } from "@/lib/database.types";

import { LANGUAGES } from "@/lib/i18n";

import { Field, Input, Select } from "./ui";

/** Farmer fields, blank for a new farmer or filled for an edit. */
export function FarmerFields({ farmer }: { farmer?: Farmer }) {
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name">
          <Input name="name" required defaultValue={farmer?.name} />
        </Field>
        <Field label="Your reference">
          <Input name="external_ref" placeholder="F-0042" defaultValue={farmer?.external_ref ?? ""} />
        </Field>
        <Field label="Phone">
          <Input name="phone" type="tel" defaultValue={farmer?.phone ?? ""} />
        </Field>
        <Field label="Village">
          <Input name="village" defaultValue={farmer?.village ?? ""} />
        </Field>
        <Field label="District">
          <Input name="district" defaultValue={farmer?.district ?? ""} />
        </Field>
        <Field label="State / county">
          <Input name="state" defaultValue={farmer?.state ?? ""} />
        </Field>
        <Field label="Country">
          <Input name="country" defaultValue={farmer?.country ?? ""} />
        </Field>
        <Field label="Language" hint="For their statement">
          <Select name="language" defaultValue={farmer?.language ?? "en"}>
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>
                {l.native} ({l.label})
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <h2 className="mt-2 text-sm font-semibold">Consent and rights</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Consent signed on">
          <Input name="consent_on" type="date" defaultValue={farmer?.consent_on ?? ""} />
        </Field>
        <Field label="Consent reference">
          <Input name="consent_reference" defaultValue={farmer?.consent_reference ?? ""} />
        </Field>
        <Field label="Carbon rights agreement">
          <Input name="carbon_rights_ref" placeholder="CRA/2025/0042" defaultValue={farmer?.carbon_rights_ref ?? ""} />
        </Field>
        <Field label="Signed on">
          <Input name="carbon_rights_signed_on" type="date" defaultValue={farmer?.carbon_rights_signed_on ?? ""} />
        </Field>
      </div>
      <h2 className="mt-2 text-sm font-semibold">Payouts</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Method">
          <Select name="payout_method" defaultValue={farmer?.payout_method ?? ""}>
            <option value="">Not set</option>
            <option value="upi">UPI</option>
            <option value="bank">Bank transfer</option>
            <option value="mobile_money">Mobile money</option>
            <option value="cash">Cash</option>
            <option value="other">Other</option>
          </Select>
        </Field>
        <Field label="Handle" hint="A masked handle only (e.g. ****4821). Never store full account numbers here.">
          <Input name="payout_reference" defaultValue={farmer?.payout_reference ?? ""} />
        </Field>
      </div>
    </>
  );
}

/** Project fields, blank for a new project or filled for an edit. */
export function ProjectFields({ project }: { project?: Project }) {
  return (
    <>
      <Field label="Name">
        <Input name="name" required placeholder="e.g. Cauvery Delta AWD" defaultValue={project?.name} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Pathway" hint={project ? "Fixed once farms are estimated under it." : "The engine estimates rice and agroforestry today."}>
          <Select name="pathway" defaultValue={project?.pathway ?? "rice"} disabled={!!project}>
            <option value="rice">Rice methane (AWD) — VM0051</option>
            <option value="agroforestry">Agroforestry / ARR — VM0047</option>
            <option value="soil">Soil carbon — VM0042</option>
            <option value="other">Other</option>
          </Select>
        </Field>
        <Field label="Methodology" hint="Defaults from the pathway.">
          <Input name="methodology" placeholder="VM0051" defaultValue={project?.methodology ?? ""} disabled={!!project} />
        </Field>
        <Field label="Registry">
          <Select name="registry" defaultValue={project ? (project.registry ?? "") : "Verra"}>
            <option>Verra</option>
            <option>Gold Standard</option>
            <option>Puro.earth</option>
            <option>Isometric</option>
            <option value="">Not decided</option>
          </Select>
        </Field>
        <Field label="Crediting period (years)">
          <Input name="crediting_period_yrs" type="number" min={1} max={100} defaultValue={project?.crediting_period_yrs ?? 7} />
        </Field>
        <Field label="Country">
          <Input name="country" defaultValue={project?.country ?? ""} />
        </Field>
        <Field label="Region">
          <Input name="region" defaultValue={project?.region ?? ""} />
        </Field>
        <Field label="Start date">
          <Input name="start_date" type="date" defaultValue={project?.start_date ?? ""} />
        </Field>
        {project && (
          <Field label="Status">
            <Select name="status" defaultValue={project.status}>
              <option value="design">Design</option>
              <option value="listed">Listed</option>
              <option value="registered">Registered</option>
              <option value="closed">Closed</option>
            </Select>
          </Field>
        )}
      </div>
    </>
  );
}
