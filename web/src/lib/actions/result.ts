import { DEMO } from "@/lib/env";

export type ActionResult = { error?: string; message?: string; ok?: boolean; id?: string };

export const DEMO_REFUSAL: ActionResult = {
  error:
    "This is the read-only demo. Connect Supabase (see web/README.md) to sign up and save your own data.",
};

/** Every write starts with this, so the demo can never pretend to save. */
export function refuseInDemo(): ActionResult | null {
  return DEMO ? DEMO_REFUSAL : null;
}

export function str(form: FormData, key: string): string | null {
  const v = form.get(key);
  if (typeof v !== "string") return null;
  const t = v.trim();
  return t === "" ? null : t;
}

export function num(form: FormData, key: string): number | null {
  const s = str(form, key);
  if (s === null) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

/** Postgres and PostgREST errors, said plainly. */
export function explain(message: string): string {
  if (/row-level security|permission denied/i.test(message)) {
    return "Your role in this organisation does not allow that.";
  }
  if (/duplicate key/i.test(message)) return "That reference is already in use in this organisation.";
  if (/violates check constraint/i.test(message)) return `A value is out of range (${message}).`;
  return message;
}
