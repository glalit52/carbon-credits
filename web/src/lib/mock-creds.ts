import type { Role } from "@/lib/database.types";

export interface MockUserCredential {
  email: string;
  password: string;
  name: string;
  role: Role;
  title: string;
  department: string;
  avatarInitials: string;
  description: string;
  permissions: string[];
}

export const MOCK_USERS: MockUserCredential[] = [
  {
    email: "admin@carbonstack.io",
    password: "CarbonStack2026!",
    name: "Priya Raman",
    role: "owner",
    title: "Project Director & Organization Owner",
    department: "Executive Management",
    avatarInitials: "PR",
    description: "Full administrative authority: project creation, vintage approval, issuance signing, and treasury payments.",
    permissions: [
      "Full Organization Management",
      "Vintage Issuance Signing",
      "Farmer Treasury Payments",
      "API & Integration Access",
      "Four-Eyes Final Review",
    ],
  },
  {
    email: "analyst@carbonstack.io",
    password: "CarbonStack2026!",
    name: "Ravi Shankar",
    role: "analyst",
    title: "Lead Carbon Quantification Analyst",
    department: "Remote Sensing & MRV",
    avatarInitials: "RS",
    description: "Methodology specialist: runs credit estimation engine, imports GIS boundaries, and submits vintages for review.",
    permissions: [
      "Run Farm & Project Estimates",
      "Batch GIS & Field Imports",
      "Methodology Compliance Modeling",
      "Submit Vintages for Four-Eyes Review",
    ],
  },
  {
    email: "verifier@carbonstack.io",
    password: "CarbonStack2026!",
    name: "Anjali Iyer",
    role: "reviewer",
    title: "Independent VVB & Four-Eyes Reviewer",
    department: "Audit & Verification",
    avatarInitials: "AI",
    description: "Independent audit authority: reviews telemetry evidence packs, radar water calls, and approves or holds vintages.",
    permissions: [
      "Four-Eyes Vintage Review",
      "Evidence Pack Verification",
      "Audit Log Inspection",
      "Hold or Approve Issuances",
    ],
  },
  {
    email: "field@carbonstack.io",
    password: "CarbonStack2026!",
    name: "Muthu Kumar",
    role: "field_agent",
    title: "Senior Agronomic Field Officer",
    department: "Field Operations & Farmer Enrolment",
    avatarInitials: "MK",
    description: "Field operative: enrols farmers on mobile, walks GPS parcel boundaries, and collects soil samples.",
    permissions: [
      "Offline Mobile GPS Walk",
      "Farmer Consent & Document Upload",
      "Tenure Paperwork Recording",
      "Water Control Verification",
    ],
  },
  {
    email: "priya@demo.carbonstack.dev",
    password: "CarbonStack2026!",
    name: "Priya Raman",
    role: "owner",
    title: "Organization Owner (Demo Account)",
    department: "Executive",
    avatarInitials: "PR",
    description: "Built-in pilot team owner.",
    permissions: ["Full Administrative Access"],
  },
  {
    email: "daniel@demo.carbonstack.dev",
    password: "CarbonStack2026!",
    name: "Daniel Otieno",
    role: "admin",
    title: "East Africa Operations Lead",
    department: "Regional Administration",
    avatarInitials: "DO",
    description: "Nyeri Aberdare pilot coordinator.",
    permissions: ["Administer Members & Data"],
  },
  {
    email: "muthu@demo.carbonstack.dev",
    password: "CarbonStack2026!",
    name: "Muthu Kumar",
    role: "field_agent",
    title: "Kaveri Basin Field Agent",
    department: "Field Enrolment",
    avatarInitials: "MK",
    description: "Thanjavur pilot field officer.",
    permissions: ["Field Enrolment & GPS"],
  },
];

export const MOCK_USER_COOKIE = "mock_user_email";

/** Find a mock user by email (case-insensitive). */
export function findMockUser(email: string | null | undefined): MockUserCredential | null {
  if (!email) return null;
  const clean = email.trim().toLowerCase();
  return MOCK_USERS.find((u) => u.email.toLowerCase() === clean) ?? null;
}

/** Verify if credentials match any mock user. */
export function verifyMockCredentials(email: string, password: string): MockUserCredential | null {
  const user = findMockUser(email);
  if (!user) return null;
  // Accepts user's password, standard master password, or demo shortcut
  if (
    password === user.password ||
    password === "CarbonStack2026!" ||
    password === "demo123456"
  ) {
    return user;
  }
  return null;
}
