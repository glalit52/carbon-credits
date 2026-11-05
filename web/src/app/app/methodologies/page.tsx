import {
  Droplets,
  TreePine,
} from "lucide-react";
import type { Metadata } from "next";

import { Badge, Card, CardHeader, PageHeader, Table, Td, Th } from "@/components/ui";

export const metadata: Metadata = { title: "Methodologies & Standards Guide" };

export default function MethodologiesPage() {
  return (
    <>
      <PageHeader
        title="Methodologies & Carbon Standards Reference"
        crumbs={[{ href: "/app", label: "App" }, { href: "/app/methodologies", label: "Methodologies" }]}
        description="Comprehensive technical reference for Verra VM0051, VM0047, and VM0042, including IPCC equations, allometric models, and deduction rules."
      />

      <div className="grid gap-6">
        {/* VM0051 Deep Dive */}
        <Card className="border-l-4 border-l-brand">
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <Droplets className="h-5 w-5 text-brand" />
                <span className="text-base font-bold">Verra VM0051 · Improved Rice Management (Methane Avoidance)</span>
              </div>
            }
            description="The premier VCS methodology for Alternate Wetting & Drying (AWD) in paddy rice, CORSIA eligible."
            action={<Badge tone="brand">CORSIA Eligible</Badge>}
          />
          <div className="p-5 flex flex-col gap-4 text-xs sm:text-sm">
            <p className="text-muted leading-relaxed">
              VM0051 credits avoided atmospheric methane emissions when farmers practice structured field aeration (AWD) instead of continuous flooding.
              Anaerobic methanogenesis is curtailed during dry-downs.
            </p>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-border bg-surface-2/40 p-3">
                <span className="text-xs text-muted uppercase font-semibold">Eligibility Scope</span>
                <div className="font-semibold text-text mt-1">Irrigated Lowland Only</div>
                <p className="text-[11px] text-muted mt-1">
                  Upland, rainfed, and deepwater paddy are excluded because drainage cannot be reliably controlled.
                </p>
              </div>

              <div className="rounded-xl border border-border bg-surface-2/40 p-3">
                <span className="text-xs text-muted uppercase font-semibold">Non-Permanence Buffer</span>
                <div className="font-bold text-brand mt-1">0% Buffer Pool</div>
                <p className="text-[11px] text-muted mt-1">
                  Avoided methane was never sequestered in a vulnerable biological stock, so it cannot reverse. Zero buffer deduction applies.
                </p>
              </div>

              <div className="rounded-xl border border-border bg-surface-2/40 p-3">
                <span className="text-xs text-muted uppercase font-semibold">Global Warming Potential</span>
                <div className="font-semibold text-text mt-1">GWP100 = 28.0</div>
                <p className="text-[11px] text-muted mt-1">
                  100-year metric from IPCC Fifth Assessment Report (AR5). 1 kg of avoided CH₄ equals 28 kg CO₂e.
                </p>
              </div>
            </div>

            <div className="rounded-xl bg-surface-2 p-3 font-mono text-xs leading-relaxed">
              <span className="font-sans font-semibold text-xs text-brand block mb-1">Standard Equation:</span>
              ΔCH₄ (kg) = Baseline_EF × Total_Days × Area_ha × (1 - SF_awd)
              <br />
              Credits (tCO₂e) = (ΔCH₄ × 28.0) / 1000 - Uncertainty_Penalty
            </div>
          </div>
        </Card>

        {/* VM0047 Deep Dive */}
        <Card className="border-l-4 border-l-emerald-600">
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <TreePine className="h-5 w-5 text-emerald-600" />
                <span className="text-base font-bold">Verra VM0047 · Afforestation, Reforestation & Revegetation (ARR)</span>
              </div>
            }
            description="Dynamic performance benchmark crediting tree growth net of regional control plots."
            action={<Badge tone="neutral">Carbon Removal</Badge>}
          />
          <div className="p-5 flex flex-col gap-4 text-xs sm:text-sm">
            <p className="text-muted leading-relaxed">
              Quantifies carbon removal into woody biomass across agroforestry shade stands (e.g. Grevillea in coffee) and woodlots.
              Supports both stem-level census counts and remote-sensing canopy stocking indices.
            </p>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-border bg-surface-2/40 p-3">
                <span className="text-xs text-muted uppercase font-semibold">Allometric Biomass Model</span>
                <div className="font-semibold text-text mt-1">Power-Law Allometry</div>
                <p className="text-[11px] text-muted mt-1">
                  AGB = a · H^b. Above-ground biomass combined with below-ground root ratio (BGB = 0.27 · AGB).
                </p>
              </div>

              <div className="rounded-xl border border-border bg-surface-2/40 p-3">
                <span className="text-xs text-muted uppercase font-semibold">Non-Permanence Buffer</span>
                <div className="font-semibold text-accent mt-1">15% Risk Reserve</div>
                <p className="text-[11px] text-muted mt-1">
                  Deposited into Verra&apos;s pooled AFOLU buffer account to hedge against fire, pest, or drought loss.
                </p>
              </div>

              <div className="rounded-xl border border-border bg-surface-2/40 p-3">
                <span className="text-xs text-muted uppercase font-semibold">Dynamic Baseline</span>
                <div className="font-semibold text-text mt-1">Performance Benchmark</div>
                <p className="text-[11px] text-muted mt-1">
                  Baseline re-derived at each verification against what comparable unmanaged regional plots actually did.
                </p>
              </div>
            </div>
          </div>
        </Card>

        {/* Methodology Precision Tier Table */}
        <Card>
          <CardHeader
            title="The Precision Penalty: Asset Pricing by Measurement Tier"
            description="How owning locally calibrated measurement hardware (e.g. eddy covariance flux towers) multiplies issuable credits."
          />
          <Table>
            <thead>
              <tr>
                <Th>Measurement Asset Tier</Th>
                <Th>Data Source</Th>
                <Th>Relative Uncertainty (1σ)</Th>
                <Th>Verra Allowance</Th>
                <Th>Uncertainty Deduction</Th>
                <Th>Commercial Impact</Th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <Td className="font-bold text-xs">Tier 1 Generic</Td>
                <Td className="text-xs text-muted">IPCC Global Defaults</Td>
                <Td className="tabular text-xs">±50%</Td>
                <Td className="tabular text-xs">15%</Td>
                <Td className="tabular text-xs font-semibold text-danger">35% deducted</Td>
                <Td className="text-xs text-muted">Loses over a third of issuable credits to error penalty.</Td>
              </tr>
              <tr>
                <Td className="font-bold text-xs">Tier 2 Regional</Td>
                <Td className="text-xs text-muted">National Agronomic GHG Inventories</Td>
                <Td className="tabular text-xs">±30%</Td>
                <Td className="tabular text-xs">15%</Td>
                <Td className="tabular text-xs font-semibold text-accent">15% deducted</Td>
                <Td className="text-xs text-muted">Moderate reduction in deduction.</Td>
              </tr>
              <tr className="bg-brand-soft/20">
                <Td className="font-bold text-xs text-brand-strong">Tier 3 Calibrated</Td>
                <Td className="text-xs font-medium text-brand">Flux Towers / Local Destructive Harvest</Td>
                <Td className="tabular text-xs font-bold text-brand">±12%</Td>
                <Td className="tabular text-xs">15%</Td>
                <Td className="tabular text-xs font-bold text-brand">0% deduction (Full Credits)</Td>
                <Td className="text-xs font-semibold text-brand-strong">Issues 1.5x credits for identical physical farming practice!</Td>
              </tr>
            </tbody>
          </Table>
        </Card>
      </div>
    </>
  );
}
