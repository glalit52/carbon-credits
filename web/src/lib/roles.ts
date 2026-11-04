import type { Role } from "@/lib/database.types";

// Mirrors can_enrol / can_manage / can_administer in the migration. The
// database enforces these; the app uses them only to hide buttons a user
// could not use anyway.

export const ROLE_LABEL: Record<Role, string> = {
  owner: "Owner",
  admin: "Admin",
  reviewer: "Reviewer",
  analyst: "Analyst",
  field_agent: "Field agent",
  viewer: "Viewer",
};

export const ROLE_HELP: Record<Role, string> = {
  owner: "Everything, including other owners",
  admin: "Members, payments, issuance and all data",
  reviewer: "Approves or holds vintages (never their own)",
  analyst: "Projects, estimates, imports; submits vintages",
  field_agent: "Enrols farmers and farms, records practices and soil samples",
  viewer: "Read-only",
};

export const INVITABLE: Exclude<Role, "owner">[] = [
  "admin",
  "reviewer",
  "analyst",
  "field_agent",
  "viewer",
];

export const can = {
  enrol: (r: Role | null) => !!r && ["owner", "admin", "analyst", "field_agent"].includes(r),
  manage: (r: Role | null) => !!r && ["owner", "admin", "analyst"].includes(r),
  review: (r: Role | null) => !!r && ["owner", "admin", "reviewer"].includes(r),
  administer: (r: Role | null) => !!r && ["owner", "admin"].includes(r),
};
