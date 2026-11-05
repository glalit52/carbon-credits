"use client";

import { X } from "lucide-react";

import { Badge, Button } from "@/components/ui";
import type { SavedFieldRecord } from "@/lib/saved-locations-store";

interface FieldComparatorProps {
  fields: SavedFieldRecord[];
  onClose: () => void;
  onSelectField: (field: SavedFieldRecord) => void;
}

export function FieldComparator({ fields, onClose, onSelectField }: FieldComparatorProps) {
  if (fields.length === 0) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
      <div className="relative w-full max-w-5xl max-h-[90vh] overflow-y-auto rounded-2xl bg-surface border border-border shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-surface px-6 py-4">
          <div>
            <h2 className="text-lg font-bold text-text">Field & Practice Comparison</h2>
            <p className="text-xs text-muted">
              Side-by-side evaluation of {fields.length} candidate fields on carbon yield, financial margin, and precision economics.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-text transition"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs sm:text-sm border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="py-3 px-4 font-semibold text-muted uppercase text-xs w-1/4">Metric</th>
                  {fields.map((f) => (
                    <th key={f.id} className="py-3 px-4 font-bold text-text">
                      <div className="flex flex-col gap-1">
                        <button
                          type="button"
                          onClick={() => onSelectField(f)}
                          className="text-left font-bold text-sm text-text hover:text-brand transition"
                          title="Click to load this field in checker"
                        >
                          {f.name}
                        </button>
                        <div className="flex items-center gap-1.5 font-normal">
                          <Badge tone="neutral">{f.result.methodology}</Badge>
                          <Badge tone={f.result.eligibility === "PASS" ? "brand" : "accent"}>
                            {f.result.eligibility}
                          </Badge>
                        </div>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {/* General Info */}
                <tr className="bg-surface-2/30">
                  <td colSpan={fields.length + 1} className="py-2 px-4 font-semibold text-xs uppercase text-muted">
                    Site Characteristics
                  </td>
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-medium text-muted">Pathway / Track</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-2.5 px-4 capitalize font-semibold">
                      {f.input.pathway}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-medium text-muted">Practice</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-2.5 px-4 capitalize">
                      {f.input.practice.replace(/_/g, " ")}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-medium text-muted">Area (Hectares / Acres)</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-2.5 px-4 tabular">
                      {f.input.area_ha.toFixed(2)} ha ({(f.input.area_ha * 2.471).toFixed(2)} ac)
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-medium text-muted">Centroid Coordinates</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-2.5 px-4 tabular text-xs text-muted">
                      {f.input.lat.toFixed(5)}, {f.input.lon.toFixed(5)}
                    </td>
                  ))}
                </tr>

                {/* Carbon Metrics */}
                <tr className="bg-surface-2/30">
                  <td colSpan={fields.length + 1} className="py-2 px-4 font-semibold text-xs uppercase text-muted">
                    Carbon Quantification & Deductions
                  </td>
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-medium text-muted">Gross Physical Abatement</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-2.5 px-4 tabular">
                      {f.result.grossAbatementTonnesYear} tCO2e/yr
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-medium text-muted">Buffer Pool Deduction</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-2.5 px-4 tabular text-accent">
                      -{f.result.bufferDeductionTonnes} t ({f.result.bufferDeductionPct}%)
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-medium text-muted">Uncertainty Penalty</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-2.5 px-4 tabular text-accent">
                      -{f.result.uncertaintyDeductionTonnes} t ({f.result.uncertaintyDeductionPct}%)
                    </td>
                  ))}
                </tr>
                <tr className="bg-brand-soft/20">
                  <td className="py-3 px-4 font-bold text-brand-strong">Net Verified Credits</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-3 px-4 tabular text-base font-bold text-brand">
                      {f.result.netCreditsTonnesYear} tCO2e/yr
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-medium text-muted">Per Hectare Yield</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-2.5 px-4 tabular font-medium">
                      {f.result.yieldPerHectare.toFixed(2)} t / ha
                    </td>
                  ))}
                </tr>

                {/* Financial Commercials */}
                <tr className="bg-surface-2/30">
                  <td colSpan={fields.length + 1} className="py-2 px-4 font-semibold text-xs uppercase text-muted">
                    Financial & Farmer Economics
                  </td>
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-medium text-muted">Annual Gross Revenue</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-2.5 px-4 tabular font-semibold">
                      ${f.result.annualGrossRevenueUSD.toLocaleString()} / yr
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-medium text-muted">Farmer Fair Payout</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-2.5 px-4 tabular font-bold text-brand-strong">
                      ${f.result.annualFarmerPayoutUSD.toLocaleString()} / yr ({f.input.farmer_share_pct ?? 60}%)
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-medium text-muted">Marginal Monitoring Cost</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-2.5 px-4 tabular text-muted">
                      ${f.result.annualMonitoringCostUSD.toLocaleString()} / yr
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-medium text-muted">Developer Net Annual Margin</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-2.5 px-4 tabular font-semibold">
                      ${f.result.annualNetMarginUSD.toLocaleString()} / yr ({f.result.marginPct.toFixed(1)}%)
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-medium text-muted">Breakeven Carbon Price</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-2.5 px-4 tabular">
                      ${f.result.breakevenPriceUSD.toFixed(2)} / credit
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-medium text-muted">10-Year Cumulative Volume</td>
                  {fields.map((f) => (
                    <td key={f.id} className="py-2.5 px-4 tabular font-medium text-brand">
                      {f.result.projections10YearTotalNetT.toLocaleString()} tCO2e
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-border bg-surface px-6 py-4">
          <div className="text-xs text-muted">
            All comparisons are normalized to standardized IPCC / Verra accounting principles.
          </div>
          <Button type="button" variant="secondary" onClick={onClose}>
            Close Comparison
          </Button>
        </div>
      </div>
    </div>
  );
}
