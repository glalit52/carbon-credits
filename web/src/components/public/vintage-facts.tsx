import { Badge } from "@/components/ui";
import type { PublicVintage } from "@/lib/database.types";
import { buyerLanguage } from "@/lib/claims";
import { fmt } from "@/lib/format";

export function VintageFacts({ v }: { v: PublicVintage }) {
  const c = v.claim_basis;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
      <dt className="text-muted">Issued by</dt>
      <dd>{v.organisation}</dd>
      <dt className="text-muted">Project</dt>
      <dd>
        {v.project}
        <div className="text-xs text-muted">{[v.region, v.country].filter(Boolean).join(", ")}</div>
      </dd>
      <dt className="text-muted">Methodology</dt>
      <dd>
        {v.methodology}
        {v.registry ? ` · ${v.registry}` : ""}
      </dd>
      <dt className="text-muted">Vintage</dt>
      <dd>
        {v.vintage_year} · serials {v.org_code}-{v.vintage_year}-{v.serial_start} to {v.serial_end}
        {v.issued_at && <div className="text-xs text-muted">issued {fmt.date(v.issued_at)}</div>}
      </dd>
      <dt className="text-muted">Claim basis</dt>
      <dd>
        <div className="flex flex-wrap gap-1">
          <Badge tone={c.offsettable_credits > 0 ? "brand" : "neutral"}>
            {c.offsettable_credits > 0 ? "Corresponding adjustment applied" : "No corresponding adjustment"}
          </Badge>
          {c.corsia_eligible && <Badge tone="info">CORSIA eligible</Badge>}
        </div>
        <p className="mt-1 text-xs text-muted">{buyerLanguage(c, v.country)}</p>
      </dd>
    </dl>
  );
}
