// Types for supabase/migrations/*_core.sql, written to match it column for
// column. Regenerate with `supabase gen types typescript --linked` once a
// project is linked, and keep the hand-written aliases at the bottom.

export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[];

type Table<Row, Required extends keyof Row = never> = {
  Row: Row;
  Insert: Partial<Row> & Pick<Row, Required>;
  Update: Partial<Row>;
  Relationships: [];
};

export type Role = "owner" | "admin" | "reviewer" | "analyst" | "field_agent" | "viewer";
export type Pathway = "rice" | "agroforestry" | "soil" | "other";
export type VintageStatus = "draft" | "submitted" | "approved" | "on_hold" | "issued";
export type PaymentStatus = "pending" | "approved" | "paid" | "failed";
export type Tenure =
  | "owned_title"
  | "registered_lease"
  | "community_right"
  | "grama_sabha_consent"
  | "undocumented";
export type RiceEcosystem = "irrigated_lowland" | "rainfed" | "upland" | "deepwater" | "unknown";
export type WaterControl = "full" | "irrigation_only" | "none" | "unknown";
export type FarmSource = "drawn" | "uploaded" | "imported" | "gps" | "api";
export type FarmStatus = "draft" | "enrolled" | "blocked" | "withdrawn";

export type Season = {
  name: string;
  start_month: number;
  start_day: number;
  end_month: number;
  end_day: number;
};

export type PolygonGeometry =
  | { type: "Polygon"; coordinates: number[][][] }
  | { type: "MultiPolygon"; coordinates: number[][][][] };

export type Profile = {
  id: string;
  full_name: string | null;
  phone: string | null;
  created_at: string;
};

export type Organization = {
  id: string;
  name: string;
  kind: "developer" | "aggregator" | "buyer" | "verifier";
  country: string | null;
  created_by: string | null;
  created_at: string;
};

export type Membership = {
  org_id: string;
  user_id: string;
  role: Role;
  created_at: string;
};

export type Invitation = {
  id: string;
  org_id: string;
  email: string;
  role: Exclude<Role, "owner">;
  token: string;
  invited_by: string | null;
  accepted_at: string | null;
  expires_at: string;
  created_at: string;
};

export type Project = {
  id: string;
  org_id: string;
  name: string;
  pathway: Pathway;
  methodology: string;
  registry: string | null;
  country: string | null;
  region: string | null;
  start_date: string | null;
  crediting_period_yrs: number | null;
  status: "design" | "listed" | "registered" | "closed";
  created_by: string | null;
  created_at: string;
};

export type Farmer = {
  id: string;
  org_id: string;
  name: string;
  phone: string | null;
  village: string | null;
  district: string | null;
  state: string | null;
  country: string | null;
  external_ref: string | null;
  consent_on: string | null;
  consent_reference: string | null;
  carbon_rights_ref: string | null;
  carbon_rights_signed_on: string | null;
  payout_method: "bank" | "upi" | "mobile_money" | "cash" | "other" | null;
  payout_reference: string | null;
  created_by: string | null;
  created_at: string;
};

export type Farm = {
  id: string;
  org_id: string;
  project_id: string | null;
  farmer_id: string | null;
  name: string;
  external_ref: string | null;
  boundary: PolygonGeometry;
  area_ha: number;
  centroid_lat: number;
  centroid_lon: number;
  crop: string | null;
  practice: string | null;
  tenure: Tenure | null;
  tenure_reference: string | null;
  rice_ecosystem: RiceEcosystem | null;
  water_control: WaterControl | null;
  stems_planted: number | null;
  species: string[] | null;
  enrolled_on: string | null;
  seasons: Season[];
  source: FarmSource;
  status: FarmStatus;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type PracticeRecord = {
  id: string;
  org_id: string;
  farm_id: string;
  year: number;
  season: string | null;
  practice: string;
  started_on: string | null;
  ended_on: string | null;
  evidence_path: string | null;
  notes: string | null;
  recorded_by: string | null;
  created_at: string;
};

export type SoilSample = {
  id: string;
  org_id: string;
  farm_id: string;
  sampled_on: string;
  depth_top_cm: number;
  depth_bottom_cm: number;
  soc_pct: number;
  bulk_density: number | null;
  lab: string | null;
  lab_reference: string | null;
  recorded_by: string | null;
  created_at: string;
};

export type ImportRun = {
  id: string;
  org_id: string;
  kind: "farms" | "farmers" | "practices" | "soil";
  filename: string | null;
  row_count: number;
  ok_count: number;
  error_count: number;
  errors: Json;
  created_by: string | null;
  created_at: string;
};

export type Estimate = {
  id: string;
  org_id: string;
  farm_id: string;
  year: number;
  methodology: string;
  gross_t: number;
  net_t: number;
  data_quality: string;
  input: Json;
  result: Json;
  engine_version: string | null;
  requested_by: string | null;
  created_at: string;
};

export type Vintage = {
  id: string;
  org_id: string;
  project_id: string;
  year: number;
  gross_t: number;
  net_t: number;
  issuable: number;
  status: VintageStatus;
  derivation: Json;
  submitted_by: string | null;
  approved_by: string | null;
  serial_start: number | null;
  serial_end: number | null;
  created_at: string;
  updated_at: string;
};

export type VintageEvent = {
  id: number;
  org_id: string;
  vintage_id: string;
  from_status: VintageStatus | null;
  to_status: VintageStatus;
  note: string | null;
  actor: string | null;
  at: string;
};

export type Payment = {
  id: string;
  org_id: string;
  vintage_id: string;
  farmer_id: string;
  credits: number;
  amount: number;
  currency: string;
  status: PaymentStatus;
  due_on: string | null;
  paid_on: string | null;
  reference: string | null;
  created_at: string;
};

export type Integration = {
  id: string;
  org_id: string;
  provider: string;
  enabled: boolean;
  config: Json;
  last_sync_at: string | null;
  last_status: string | null;
  created_at: string;
};

export type AuditEvent = {
  id: number;
  org_id: string;
  actor: string | null;
  action: string;
  entity: string;
  entity_id: string | null;
  detail: Json | null;
  at: string;
};

export type AuthorisedUse = "other_party_ndc" | "corsia" | "other_international_mitigation_purposes";
export type RetirementPurpose = "contribution" | "offset" | "corsia";

export type Authorisation = {
  id: string;
  org_id: string;
  project_id: string;
  authority: string;
  reference: string;
  issued_on: string;
  authorised_use: AuthorisedUse;
  authorised_volume_t: number;
  adjustment_committed: boolean;
  first_vintage: number;
  last_vintage: number;
  valid_until: string | null;
  revoked_on: string | null;
  created_by: string | null;
  created_at: string;
};

export type Adjustment = {
  id: string;
  org_id: string;
  authorisation_id: string;
  vintage_year: number;
  volume_t: number;
  reported_on: string;
  reference: string;
  created_by: string | null;
  created_at: string;
};

export type Retirement = {
  id: string;
  org_id: string;
  vintage_id: string;
  serial_start: number;
  serial_end: number;
  quantity: number;
  beneficiary: string;
  purpose: RetirementPurpose;
  claim: string;
  retired_by: string | null;
  retired_at: string;
};

/** public.claim_basis(): what a vintage permits a buyer to say. */
export type ClaimBasis = {
  basis: "unadjusted_voluntary" | "authorised_itmo";
  authorisation: { reference: string; authority: string; authorised_use: AuthorisedUse; adjustment_committed: boolean } | null;
  adjusted_t: number;
  offsettable_credits: number;
  offset_remaining: number;
  corsia_eligible: boolean;
  reasons: string[];
};

/** public.public_vintage(): registry facts anyone may see. */
export type PublicVintage = {
  organisation: string;
  org_code: string;
  project: string;
  methodology: string;
  registry: string | null;
  country: string | null;
  region: string | null;
  vintage_year: number;
  net_t: number;
  serial_start: number;
  serial_end: number;
  issued_at: string | null;
  claim_basis: ClaimBasis;
};

export type PublicRetirement = Pick<
  Retirement,
  "id" | "beneficiary" | "purpose" | "claim" | "retired_at" | "serial_start" | "serial_end" | "quantity"
>;

export type VerifyResult =
  | { found: false; reason?: string }
  | { found: true; serial: number; code: string; vintage: PublicVintage; retirement: PublicRetirement | null };

export type CertificateResult = { found: false } | ({ found: true; vintage: PublicVintage } & PublicRetirement);

export type Database = {
  public: {
    Tables: {
      profiles: Table<Profile, "id">;
      organizations: Table<Organization, "name">;
      memberships: Table<Membership, "org_id" | "user_id" | "role">;
      invitations: Table<Invitation, "org_id" | "email" | "role">;
      projects: Table<Project, "org_id" | "name" | "pathway" | "methodology">;
      farmers: Table<Farmer, "org_id" | "name">;
      farms: Table<
        Farm,
        "org_id" | "name" | "boundary" | "area_ha" | "centroid_lat" | "centroid_lon"
      >;
      practice_records: Table<PracticeRecord, "org_id" | "farm_id" | "year" | "practice">;
      soil_samples: Table<
        SoilSample,
        "org_id" | "farm_id" | "sampled_on" | "depth_top_cm" | "depth_bottom_cm" | "soc_pct"
      >;
      imports: Table<ImportRun, "org_id" | "kind">;
      estimates: Table<
        Estimate,
        | "org_id"
        | "farm_id"
        | "year"
        | "methodology"
        | "gross_t"
        | "net_t"
        | "data_quality"
        | "input"
        | "result"
      >;
      vintages: Table<Vintage, "org_id" | "project_id" | "year">;
      vintage_events: Table<VintageEvent, "org_id" | "vintage_id" | "to_status">;
      payments: Table<Payment, "org_id" | "vintage_id" | "farmer_id" | "credits" | "amount">;
      integrations: Table<Integration, "org_id" | "provider">;
      audit_events: Table<AuditEvent, "org_id" | "action" | "entity">;
      authorisations: Table<
        Authorisation,
        | "org_id"
        | "project_id"
        | "authority"
        | "reference"
        | "issued_on"
        | "authorised_use"
        | "authorised_volume_t"
        | "adjustment_committed"
        | "first_vintage"
        | "last_vintage"
      >;
      adjustments: Table<Adjustment, "org_id" | "authorisation_id" | "vintage_year" | "volume_t" | "reported_on" | "reference">;
      retirements: Table<Retirement, "org_id" | "vintage_id" | "serial_start" | "serial_end" | "beneficiary" | "purpose" | "claim">;
    };
    Views: { [_ in never]: never };
    Functions: {
      create_organization: {
        Args: { org_name: string; org_kind?: string; org_country?: string | null };
        Returns: string;
      };
      accept_invitation: { Args: { invite_token: string }; Returns: string };
      retire_credits: {
        Args: { vintage: string; credits: number; beneficiary_name: string; retire_purpose: RetirementPurpose };
        Returns: Retirement;
      };
      vintage_claims: { Args: { org: string }; Returns: { vintage_id: string; basis: ClaimBasis }[] };
      verify_credit: { Args: { code: string }; Returns: VerifyResult };
      retirement_certificate: { Args: { retirement: string }; Returns: CertificateResult };
      transition_vintage: {
        Args: { vintage: string; to_state: VintageStatus; review_note?: string | null };
        Returns: Vintage;
      };
    };
    Enums: { [_ in never]: never };
    CompositeTypes: { [_ in never]: never };
  };
};
