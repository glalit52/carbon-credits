import "server-only";

import type {
  AuditEvent,
  Estimate,
  Farm,
  Farmer,
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

import raw from "./demo-data.json";

// Built by scripts/build_web_demo.py from the real engine. Read-only.
export type DemoData = {
  as_of: string;
  organization: Organization;
  members: { user_id: string; full_name: string; email: string; role: Role; org_id: string; created_at: string }[];
  viewer: string;
  projects: Project[];
  farmers: Farmer[];
  farms: Farm[];
  estimates: Estimate[];
  practices: PracticeRecord[];
  soil: SoilSample[];
  vintages: Vintage[];
  vintage_events: VintageEvent[];
  payments: Payment[];
  integrations: Integration[];
  audit: AuditEvent[];
  invitations: Invitation[];
};

export const demo = raw as unknown as DemoData;
