"use client";

import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  DollarSign,
  Download,
  FileCheck,
  FileSpreadsheet,
  Globe,
  Printer,
  Satellite,
  Share2,
  Sprout,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { RainBars, YearBars } from "@/components/charts";
import { Badge, Button, Card, CardHeader, Notice, Stat, Table, Td, Th } from "@/components/ui";

import type { CheckInput, CheckResult } from "@/lib/checker-engine";
import { exportFieldKML } from "@/lib/saved-locations-store";

interface FieldCheckViewProps {
  input: CheckInput;
  result: CheckResult;
  onSave: () => void;
  isSaved?: boolean;
  onPrint: () => void;
}

export function FieldCheckView({ input, result, onSave, isSaved, onPrint }: FieldCheckViewProps) {
  const [activeTab, setActiveTab] = useState<"carbon" | "financial" | "climate" | "readiness">("carbon");

  const downloadGeoJSON = () => {
    const feature = {
      type: "Feature",
      properties: {
        name: input.name,
        pathway: input.pathway,
        crop: input.crop,
        practice: input.practice,
        area_ha: input.area_ha,
        methodology: result.methodology,
        eligibility: result.eligibility,
        gross_tco2e_yr: result.grossAbatementTonnesYear,
        net_tco2e_yr: result.netCreditsTonnesYear,
        annual_revenue_usd: result.annualGrossRevenueUSD,
        annual_farmer_payout_usd: result.annualFarmerPayoutUSD,
      },
      geometry: input.boundary,
    };
    const blob = new Blob([JSON.stringify(feature, null, 2)], { type: "application/geo+json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${input.name.toLowerCase().replace(/[^a-z0-9]/g, "-")}-boundary.geojson`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadKML = () => {
    const kml = exportFieldKML({
      id: "temp",
      name: input.name,
      input,
      result,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
    const blob = new Blob([kml], { type: "application/vnd.google-earth.kml+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${input.name.toLowerCase().replace(/[^a-z0-9]/g, "-")}.kml`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const shareWhatsApp = () => {
    const text =
      `*Carbon Credit & dMRV Assessment Summary*\n` +
      `Field: ${input.name}\n` +
      `Location: ${input.lat.toFixed(5)}, ${input.lon.toFixed(5)} (${input.area_ha.toFixed(2)} ha)\n` +
      `Pathway: ${input.pathway.toUpperCase()} (${result.methodology})\n` +
      `Eligibility: ${result.eligibility}\n` +
      `Net Credits: ${result.netCreditsTonnesYear} tCO2e/year\n` +
      `Est. Annual Revenue: $${result.annualGrossRevenueUSD.toLocaleString()} USD\n` +
      `Farmer Fair Share: $${result.annualFarmerPayoutUSD.toLocaleString()} USD/year\n` +
      `Verified via carbonstack MRV Engine.`;
    window.open(`https://api.whatsapp.com/send?text=${encodeURIComponent(text)}`, "_blank");
  };

  const barChartData = result.projections5Year.map((p) => ({
    year: String(p.year),
    gross: p.gross_t,
    net: p.net_t,
  }));

  return (
    <div className="flex flex-col gap-6">
      {/* Header Banner */}
      <Card className="p-5 bg-gradient-to-r from-surface to-surface-2/60 border-l-4 border-l-brand">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted">Field Assessment Report</span>
              <Badge
                tone={result.eligibility === "PASS" ? "brand" : result.eligibility === "CONDITIONAL" ? "accent" : "danger"}
              >
                {result.eligibility === "PASS"
                  ? "✓ Eligible for Issuance"
                  : result.eligibility === "CONDITIONAL"
                  ? "⚠ Conditional Approval"
                  : "✗ Ineligible / Blocked"}
              </Badge>
              <Badge tone="neutral">{result.methodology}</Badge>
            </div>
            <h2 className="mt-1 text-2xl font-bold tracking-tight text-text">{input.name}</h2>
            <p className="text-xs text-muted mt-1">
              {input.area_ha.toFixed(2)} ha ({(input.area_ha * 2.471).toFixed(2)} acres) · Centroid:{" "}
              <span className="tabular">{input.lat.toFixed(5)}, {input.lon.toFixed(5)}</span> · Practice:{" "}
              <strong className="text-text capitalize">{input.practice.replace(/_/g, " ")}</strong>
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="secondary" onClick={onPrint} className="text-xs">
              <Printer className="h-3.5 w-3.5" /> Printable Report
            </Button>
            <Button type="button" variant="secondary" onClick={shareWhatsApp} className="text-xs">
              <Share2 className="h-3.5 w-3.5" /> Share
            </Button>
            <Button type="button" variant={isSaved ? "secondary" : "primary"} onClick={onSave} className="text-xs">
              {isSaved ? "✓ Saved" : "Save Field"}
            </Button>
          </div>
        </div>
      </Card>

      {/* Blockers & Warnings Notice */}
      {result.blockers.length > 0 && (
        <Notice tone="danger" title="Regulatory or Methodology Blockers">
          <ul className="list-disc pl-5 space-y-1 mt-1 text-xs">
            {result.blockers.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        </Notice>
      )}

      {result.warnings.length > 0 && (
        <Notice tone="accent" title="Operational Considerations">
          <ul className="list-disc pl-5 space-y-1 mt-1 text-xs">
            {result.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </Notice>
      )}

      {/* Key Numbers Grid */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Stat
          label="Net Issuable Credits"
          value={<span className="text-brand">{result.netCreditsTonnesYear} t</span>}
          hint={`${result.yieldPerHectare.toFixed(2)} tCO2e / ha / yr`}
          tone="brand"
        />
        <Stat
          label="Annual Gross Revenue"
          value={`$${result.annualGrossRevenueUSD.toLocaleString()}`}
          hint={`at $${input.carbon_price_usd ?? 15}/tCO2e credit price`}
        />
        <Stat
          label="Farmer Fair Payout"
          value={<span className="text-brand-strong">${result.annualFarmerPayoutUSD.toLocaleString()}</span>}
          hint={`${input.farmer_share_pct ?? 60}% revenue share / yr`}
          tone="brand"
        />
        <Stat
          label="Marginal MRV Cost"
          value={`$${result.annualMonitoringCostUSD.toLocaleString()}`}
          hint={`$${result.costPerIssuedTonneUSD.toFixed(2)} / issued tonne`}
        />
        <Stat
          label="Developer Net Margin"
          value={`$${result.annualNetMarginUSD.toLocaleString()}`}
          hint={`${result.marginPct.toFixed(1)}% net operating margin`}
        />
      </div>

      {/* Section Tabs */}
      <div className="flex border-b border-border text-sm">
        <button
          type="button"
          onClick={() => setActiveTab("carbon")}
          className={`flex items-center gap-2 border-b-2 px-4 py-2.5 font-medium transition ${
            activeTab === "carbon"
              ? "border-brand text-brand"
              : "border-transparent text-muted hover:border-border hover:text-text"
          }`}
        >
          <Sprout className="h-4 w-4" /> Carbon Derivation & Deductions
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("financial")}
          className={`flex items-center gap-2 border-b-2 px-4 py-2.5 font-medium transition ${
            activeTab === "financial"
              ? "border-brand text-brand"
              : "border-transparent text-muted hover:border-border hover:text-text"
          }`}
        >
          <DollarSign className="h-4 w-4" /> Financial Viability & Forecast
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("climate")}
          className={`flex items-center gap-2 border-b-2 px-4 py-2.5 font-medium transition ${
            activeTab === "climate"
              ? "border-brand text-brand"
              : "border-transparent text-muted hover:border-border hover:text-text"
          }`}
        >
          <Satellite className="h-4 w-4" /> Climate & Sentinel Radar
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("readiness")}
          className={`flex items-center gap-2 border-b-2 px-4 py-2.5 font-medium transition ${
            activeTab === "readiness"
              ? "border-brand text-brand"
              : "border-transparent text-muted hover:border-border hover:text-text"
          }`}
        >
          <FileCheck className="h-4 w-4" /> Readiness & Audit Steps
        </button>
      </div>

      {/* TAB 1: Carbon Derivation */}
      {activeTab === "carbon" && (
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader
              title="Deductions & Issuance Waterfall"
              description="Transparent methodology penalties applied to gross abatement under Verra & Gold Standard rules."
            />
            <div className="p-5">
              <div className="grid gap-3 sm:grid-cols-4">
                <div className="rounded-xl border border-border bg-surface-2/40 p-3">
                  <div className="text-xs text-muted uppercase tracking-wider">Gross Physical Abatement</div>
                  <div className="mt-1 text-xl font-semibold tabular">{result.grossAbatementTonnesYear} t</div>
                  <div className="text-xs text-muted mt-1">Calculated physical avoidance or sequestration</div>
                </div>

                <div className="rounded-xl border border-border bg-surface-2/40 p-3">
                  <div className="text-xs text-muted uppercase tracking-wider">
                    Buffer Pool ({result.bufferDeductionPct}%)
                  </div>
                  <div className="mt-1 text-xl font-semibold tabular text-accent">
                    -{result.bufferDeductionTonnes} t
                  </div>
                  <div className="text-xs text-muted mt-1">
                    {result.methodology === "VM0051"
                      ? "0% buffer: Avoided emissions never reverse"
                      : "15% non-permanence pooled risk reserve"}
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-surface-2/40 p-3">
                  <div className="text-xs text-muted uppercase tracking-wider">
                    Uncertainty Penalty ({result.uncertaintyDeductionPct}%)
                  </div>
                  <div className="mt-1 text-xl font-semibold tabular text-accent">
                    -{result.uncertaintyDeductionTonnes} t
                  </div>
                  <div className="text-xs text-muted mt-1">
                    {input.measurement_tier === 3
                      ? "0% penalty: Tier 3 local calibrated asset"
                      : `Tier ${input.measurement_tier ?? 1} generic default penalty above 15% allowance`}
                  </div>
                </div>

                <div className="rounded-xl border border-brand/40 bg-brand-soft p-3">
                  <div className="text-xs text-brand-strong uppercase tracking-wider font-semibold">
                    Net Verified Credits
                  </div>
                  <div className="mt-1 text-xl font-bold tabular text-brand">
                    {result.netCreditsTonnesYear} tCO2e/yr
                  </div>
                  <div className="text-xs text-brand-strong mt-1">Ready for registry issuance & minting</div>
                </div>
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Methodology Derivation Audit Steps"
              description={`Step-by-step mathematical calculation per ${result.methodology} specifications.`}
            />
            <Table>
              <thead>
                <tr>
                  <Th>Audit Step</Th>
                  <Th>Formula Equation</Th>
                  <Th>Calculated Value</Th>
                  <Th>Standard Citation</Th>
                </tr>
              </thead>
              <tbody>
                {result.derivationSteps.map((s, idx) => (
                  <tr key={idx} className="hover:bg-surface-2/50 transition">
                    <Td className="font-medium text-xs sm:text-sm">{s.step}</Td>
                    <Td className="font-mono text-xs text-brand-strong">{s.formula}</Td>
                    <Td className="text-xs tabular">{s.intermediateValue}</Td>
                    <Td className="text-xs text-muted">{s.sourceStandard}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
      )}

      {/* TAB 2: Financial Viability & Forecast */}
      {activeTab === "financial" && (
        <div className="flex flex-col gap-6">
          <div className="grid gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader
                title="5-Year Carbon Issuance Projections"
                description="Projected annual gross vs net creditable tonnes."
              />
              <div className="p-5">
                <YearBars
                  data={barChartData}
                  bars={[
                    { key: "gross", label: "Gross tCO2e", color: "var(--info)" },
                    { key: "net", label: "Net Issuable Credits", color: "var(--brand)" },
                  ]}
                  height={260}
                />
              </div>
            </Card>

            <Card>
              <CardHeader title="Commercial Viability Summary" />
              <div className="flex flex-col gap-3 p-5 text-sm">
                <div className="flex justify-between border-b border-border pb-2">
                  <span className="text-muted">Assumed Carbon Price</span>
                  <strong className="tabular">${input.carbon_price_usd ?? 15.0}/tCO2e</strong>
                </div>
                <div className="flex justify-between border-b border-border pb-2">
                  <span className="text-muted">Farmer Share ({input.farmer_share_pct ?? 60}%)</span>
                  <strong className="tabular text-brand-strong">${result.annualFarmerPayoutUSD.toLocaleString()}/yr</strong>
                </div>
                <div className="flex justify-between border-b border-border pb-2">
                  <span className="text-muted">Annual Monitoring & MRV</span>
                  <strong className="tabular">${result.annualMonitoringCostUSD.toLocaleString()}/yr</strong>
                </div>
                <div className="flex justify-between border-b border-border pb-2">
                  <span className="text-muted">Developer Net Annual Margin</span>
                  <strong className="tabular">${result.annualNetMarginUSD.toLocaleString()}/yr</strong>
                </div>
                <div className="flex justify-between border-b border-border pb-2">
                  <span className="text-muted">Breakeven Carbon Price</span>
                  <strong className="tabular">${result.breakevenPriceUSD.toFixed(2)}/tCO2e</strong>
                </div>
                <div className="flex justify-between pb-1">
                  <span className="text-muted">10-Year Cumulative Net Yield</span>
                  <strong className="tabular text-brand">{result.projections10YearTotalNetT.toLocaleString()} tCO2e</strong>
                </div>
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader title="Detailed Annual Payout Schedule" />
            <Table>
              <thead>
                <tr>
                  <Th>Year</Th>
                  <Th>Gross Abatement</Th>
                  <Th>Net Credits Issued</Th>
                  <Th>Cumulative Volume</Th>
                  <Th>Gross Revenue (USD)</Th>
                  <Th>Farmer Fair Payout (USD)</Th>
                </tr>
              </thead>
              <tbody>
                {result.projections5Year.map((p) => (
                  <tr key={p.year}>
                    <Td className="font-semibold text-xs sm:text-sm">{p.year}</Td>
                    <Td className="tabular text-xs">{p.gross_t} t</Td>
                    <Td className="tabular text-xs font-medium text-brand">{p.net_t} t</Td>
                    <Td className="tabular text-xs text-muted">{p.cumulative_t} t</Td>
                    <Td className="tabular text-xs">${p.revenue_usd.toLocaleString()}</Td>
                    <Td className="tabular text-xs font-semibold text-brand-strong">${p.farmer_payout_usd.toLocaleString()}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
      )}

      {/* TAB 3: Climate & Satellite Radar */}
      {activeTab === "climate" && (
        <div className="flex flex-col gap-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader
                title="Historical Climatology Normals"
                description={`Copernicus ERA5 & NASA POWER archive at ${input.lat.toFixed(4)}°, ${input.lon.toFixed(4)}°.`}
              />
              <div className="p-5 flex flex-col gap-4">
                <RainBars rain={result.climate.monthlyRainMm} />
                <div className="grid grid-cols-3 gap-2 text-center text-xs pt-3 border-t border-border">
                  <div>
                    <div className="text-muted">Mean Temp</div>
                    <div className="font-semibold text-sm tabular">{result.climate.meanTempC}°C</div>
                  </div>
                  <div>
                    <div className="text-muted">Annual Rain</div>
                    <div className="font-semibold text-sm tabular">{result.climate.annualRainfallMm} mm</div>
                  </div>
                  <div>
                    <div className="text-muted">Drought Risk</div>
                    <div className="font-semibold text-sm">{result.climate.droughtRisk}</div>
                  </div>
                </div>
              </div>
            </Card>

            <Card>
              <CardHeader
                title="Sentinel-1 SAR Radar Revisit Cadence"
                description="Simulated 5-day radar revisit passes over this field coordinate."
              />
              <div className="p-5 flex flex-col gap-4">
                <div className="grid grid-cols-3 gap-3">
                  <div className="rounded-lg bg-surface-2 p-3 text-center">
                    <div className="text-xs text-muted">Passes / Season</div>
                    <div className="text-lg font-bold tabular text-brand">{result.satelliteMRV.passesPerSeason}</div>
                  </div>
                  <div className="rounded-lg bg-surface-2 p-3 text-center">
                    <div className="text-xs text-muted">Median Revisit</div>
                    <div className="text-lg font-bold tabular">{result.satelliteMRV.medianRevisitDays} days</div>
                  </div>
                  <div className="rounded-lg bg-surface-2 p-3 text-center">
                    <div className="text-xs text-muted">Radar Reliability</div>
                    <div className="text-lg font-bold tabular text-brand">{result.satelliteMRV.radarReliabilityPct}%</div>
                  </div>
                </div>
                <p className="text-xs text-muted">
                  Sentinel-1 C-band Synthetic Aperture Radar penetrates heavy monsoon clouds, measuring water layer depth via VV/VH polarization backscatter drop.
                </p>
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader
              title="Synthetic Sentinel-1 Radar Passes & Water Regime Calls"
              description="Pass-by-pass backscatter separation and water state detection during the season."
            />
            <Table>
              <thead>
                <tr>
                  <Th>Pass #</Th>
                  <Th>Observation Date</Th>
                  <Th>VV Backscatter</Th>
                  <Th>VH Backscatter</Th>
                  <Th>Separation</Th>
                  <Th>Detected Water State</Th>
                  <Th>Confidence</Th>
                </tr>
              </thead>
              <tbody>
                {result.satelliteMRV.samplePasses.map((p) => (
                  <tr key={p.passNumber}>
                    <Td className="text-xs tabular">{p.passNumber}</Td>
                    <Td className="text-xs tabular">{p.day}</Td>
                    <Td className="text-xs tabular">{p.vv_db} dB</Td>
                    <Td className="text-xs tabular">{p.vh_db} dB</Td>
                    <Td className="text-xs tabular">{p.separation_db} dB</Td>
                    <Td className="text-xs">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                          p.state === "flooded"
                            ? "bg-info-soft text-info"
                            : p.state === "drained"
                            ? "bg-brand-soft text-brand-strong"
                            : "bg-surface-2 text-muted"
                        }`}
                      >
                        {p.state === "drained" ? "✓ Drained (AWD)" : p.state === "flooded" ? "Flooded" : "Ambiguous"}
                      </span>
                    </Td>
                    <Td className="text-xs tabular">{p.confidence}%</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
      )}

      {/* TAB 4: Readiness & Compliance */}
      {activeTab === "readiness" && (
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader
              title="Methodology Readiness Score"
              description="Readiness index to qualify for formal Verra / Gold Standard / Puro registry issuance."
            />
            <div className="p-5 flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold">Audit Readiness</span>
                <span className="text-lg font-bold text-brand tabular">{result.readinessScore}%</span>
              </div>
              <div className="h-3 w-full overflow-hidden rounded-full bg-surface-2">
                <div
                  className="h-full bg-brand transition-all duration-500 rounded-full"
                  style={{ width: `${result.readinessScore}%` }}
                />
              </div>

              <div className="grid gap-3 sm:grid-cols-2 pt-2">
                <div className="flex items-start gap-2.5 rounded-lg border border-border p-3">
                  {input.tenure !== "undocumented" ? (
                    <CheckCircle2 className="h-4 w-4 text-brand shrink-0 mt-0.5" />
                  ) : (
                    <AlertCircle className="h-4 w-4 text-danger shrink-0 mt-0.5" />
                  )}
                  <div className="text-xs">
                    <strong className="text-text block">Tenure Verification</strong>
                    {input.tenure !== "undocumented"
                      ? `Valid ${input.tenure.replace(/_/g, " ")} (${input.tenure_reference || "ref registered"})`
                      : "Missing land document or title record."}
                  </div>
                </div>

                <div className="flex items-start gap-2.5 rounded-lg border border-border p-3">
                  {input.water_control !== "none" ? (
                    <CheckCircle2 className="h-4 w-4 text-brand shrink-0 mt-0.5" />
                  ) : (
                    <AlertCircle className="h-4 w-4 text-danger shrink-0 mt-0.5" />
                  )}
                  <div className="text-xs">
                    <strong className="text-text block">Water & Infrastructure Control</strong>
                    {input.water_control !== "none"
                      ? "Infrastructure allows drainage control"
                      : "Uncontrolled water table blocks AWD crediting."}
                  </div>
                </div>
              </div>
            </div>
          </Card>

          {/* Quick Enrol into Official Platform */}
          <Card className="p-5 border-brand/50 bg-brand-soft/20">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div>
                <h3 className="font-semibold text-sm text-text">Convert to Enrolled Platform Farm</h3>
                <p className="text-xs text-muted mt-0.5">
                  Transfer this evaluated field and its polygon into your organisation&apos;s registered farms list.
                </p>
              </div>
              <Link
                href={`/app/farms/new`}
                className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-xs font-semibold text-white hover:bg-brand-strong transition"
              >
                Proceed to Add Farm <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </Card>
        </div>
      )}

      {/* Export & Download Bar */}
      <Card className="p-4 bg-surface-2/40">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-xs font-semibold text-muted uppercase tracking-wider">
            Export Field Files & Evidence
          </span>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="secondary" onClick={downloadGeoJSON} className="text-xs py-1.5">
              <Download className="h-3.5 w-3.5" /> Download GeoJSON
            </Button>
            <Button type="button" variant="secondary" onClick={downloadKML} className="text-xs py-1.5">
              <Globe className="h-3.5 w-3.5" /> Download Google Earth KML
            </Button>
            <Button type="button" variant="secondary" onClick={onPrint} className="text-xs py-1.5">
              <FileSpreadsheet className="h-3.5 w-3.5" /> Print / PDF Sheet
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
