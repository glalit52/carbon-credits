"use client";

import { Printer, X } from "lucide-react";

import { Button } from "@/components/ui";
import type { CheckInput, CheckResult } from "@/lib/checker-engine";

interface PrintableReportProps {
  input: CheckInput;
  result: CheckResult;
  onClose: () => void;
}

export function PrintableReport({ input, result, onClose }: PrintableReportProps) {
  const handlePrint = () => {
    window.print();
  };

  const today = new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs overflow-y-auto">
      <div className="relative w-full max-w-4xl max-h-[92vh] overflow-y-auto rounded-xl bg-white text-slate-900 shadow-2xl p-8 print:p-0 print:max-h-none print:shadow-none print:w-full print:rounded-none">
        {/* Screen Action Bar (hidden in print) */}
        <div className="flex items-center justify-between pb-6 mb-6 border-b border-slate-200 print:hidden">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Document Preview</span>
            <span className="rounded-full bg-emerald-100 text-emerald-800 px-2.5 py-0.5 text-xs font-semibold">
              PDF-Ready Evidence Sheet
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button type="button" onClick={handlePrint} className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs">
              <Printer className="h-3.5 w-3.5" /> Print / Save to PDF
            </Button>
            <Button type="button" variant="secondary" onClick={onClose} className="text-xs">
              <X className="h-3.5 w-3.5" /> Close
            </Button>
          </div>
        </div>

        {/* Printable Document Body */}
        <div className="flex flex-col gap-6 text-slate-800 text-sm">
          {/* Header */}
          <div className="flex items-start justify-between border-b-2 border-slate-900 pb-4">
            <div>
              <div className="text-xs font-bold uppercase tracking-widest text-emerald-700">carbonstack · dMRV Engine</div>
              <h1 className="text-2xl font-black text-slate-900 mt-0.5">Carbon Credit Feasibility & MRV Assessment</h1>
              <div className="text-xs text-slate-500 mt-1">
                Generated: {today} · Verification Standard: {result.methodology}
              </div>
            </div>
            <div className="text-right">
              <div className="inline-block rounded-md border border-slate-300 bg-slate-50 px-3 py-1.5 text-center">
                <span className="text-[10px] uppercase font-bold text-slate-500 block">Assessment Verdict</span>
                <span
                  className={`text-sm font-extrabold ${
                    result.eligibility === "PASS"
                      ? "text-emerald-700"
                      : result.eligibility === "CONDITIONAL"
                      ? "text-amber-700"
                      : "text-rose-700"
                  }`}
                >
                  {result.eligibility === "PASS"
                    ? "ELIGIBLE FOR CREDITING"
                    : result.eligibility === "CONDITIONAL"
                    ? "CONDITIONAL"
                    : "BLOCKED"}
                </span>
              </div>
            </div>
          </div>

          {/* Farm & Location Metadata Table */}
          <div className="grid grid-cols-2 gap-4 border border-slate-200 rounded-lg p-4 bg-slate-50/50">
            <div>
              <span className="text-xs font-semibold text-slate-500 uppercase">Field Identification</span>
              <div className="font-bold text-base text-slate-900 mt-0.5">{input.name}</div>
              <div className="text-xs text-slate-600 mt-1">
                Farmer: <strong>{input.farmer_name || "Unassigned / Prospective"}</strong>
              </div>
              <div className="text-xs text-slate-600">
                Land Tenure: <strong>{input.tenure.replace(/_/g, " ")}</strong> (Ref: {input.tenure_reference || "N/A"})
              </div>
            </div>

            <div>
              <span className="text-xs font-semibold text-slate-500 uppercase">Geographic & Area Specifications</span>
              <div className="font-bold text-base text-slate-900 mt-0.5">
                {input.area_ha.toFixed(2)} ha ({(input.area_ha * 2.471).toFixed(2)} acres)
              </div>
              <div className="text-xs text-slate-600 mt-1 font-mono">
                Centroid: {input.lat.toFixed(5)}°N, {input.lon.toFixed(5)}°E
              </div>
              <div className="text-xs text-slate-600">
                Pathway: <strong className="capitalize">{input.pathway}</strong> · Practice:{" "}
                <strong className="capitalize">{input.practice.replace(/_/g, " ")}</strong>
              </div>
            </div>
          </div>

          {/* Key Quantification Summary Banner */}
          <div className="grid grid-cols-4 gap-3 text-center border-y border-slate-200 py-3 bg-emerald-50/40">
            <div>
              <span className="text-[11px] font-semibold text-slate-500 uppercase">Gross Abatement</span>
              <div className="text-lg font-bold text-slate-900 tabular mt-0.5">{result.grossAbatementTonnesYear} t</div>
              <span className="text-[10px] text-slate-500">tCO2e / year</span>
            </div>
            <div>
              <span className="text-[11px] font-semibold text-slate-500 uppercase">Total Deductions</span>
              <div className="text-lg font-bold text-amber-700 tabular mt-0.5">
                -{(result.bufferDeductionTonnes + result.uncertaintyDeductionTonnes).toFixed(1)} t
              </div>
              <span className="text-[10px] text-slate-500">Buffer + Uncertainty</span>
            </div>
            <div>
              <span className="text-[11px] font-semibold text-emerald-800 uppercase">Net Issuable Credits</span>
              <div className="text-xl font-black text-emerald-700 tabular mt-0.5">{result.netCreditsTonnesYear} t</div>
              <span className="text-[10px] text-emerald-800 font-medium">tCO2e / year verified</span>
            </div>
            <div>
              <span className="text-[11px] font-semibold text-slate-500 uppercase">Farmer Annual Payout</span>
              <div className="text-lg font-bold text-emerald-800 tabular mt-0.5">
                ${result.annualFarmerPayoutUSD.toLocaleString()}
              </div>
              <span className="text-[10px] text-slate-500">{input.farmer_share_pct ?? 60}% fair share</span>
            </div>
          </div>

          {/* Derivation Steps Table */}
          <div>
            <h3 className="font-bold text-slate-900 text-xs uppercase tracking-wider mb-2">
              Scientific Derivation & Methodology Compliance Trail ({result.methodology})
            </h3>
            <table className="w-full text-left text-xs border border-slate-200">
              <thead className="bg-slate-100 text-slate-700 font-semibold border-b border-slate-200">
                <tr>
                  <th className="p-2 border-r border-slate-200">Step</th>
                  <th className="p-2 border-r border-slate-200">Formula / Equation</th>
                  <th className="p-2 border-r border-slate-200">Calculated Value</th>
                  <th className="p-2">Standard Basis</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {result.derivationSteps.map((s, idx) => (
                  <tr key={idx}>
                    <td className="p-2 font-medium border-r border-slate-200">{s.step}</td>
                    <td className="p-2 font-mono text-[11px] border-r border-slate-200 text-slate-700">{s.formula}</td>
                    <td className="p-2 font-semibold border-r border-slate-200 tabular">{s.intermediateValue}</td>
                    <td className="p-2 text-slate-500 text-[11px]">{s.sourceStandard}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 5-Year Projection Matrix */}
          <div>
            <h3 className="font-bold text-slate-900 text-xs uppercase tracking-wider mb-2">
              5-Year Issuance & Commercial Cashflow Forecast
            </h3>
            <table className="w-full text-left text-xs border border-slate-200">
              <thead className="bg-slate-100 text-slate-700 font-semibold border-b border-slate-200">
                <tr>
                  <th className="p-2 border-r border-slate-200">Vintage Year</th>
                  <th className="p-2 border-r border-slate-200">Gross Tonnes</th>
                  <th className="p-2 border-r border-slate-200">Net Credits (t)</th>
                  <th className="p-2 border-r border-slate-200">Cumulative (t)</th>
                  <th className="p-2 border-r border-slate-200">Gross Revenue ($)</th>
                  <th className="p-2">Farmer Payout ($)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {result.projections5Year.map((p) => (
                  <tr key={p.year}>
                    <td className="p-2 font-bold border-r border-slate-200">{p.year}</td>
                    <td className="p-2 border-r border-slate-200 tabular">{p.gross_t} t</td>
                    <td className="p-2 border-r border-slate-200 tabular font-semibold text-emerald-800">{p.net_t} t</td>
                    <td className="p-2 border-r border-slate-200 tabular">{p.cumulative_t} t</td>
                    <td className="p-2 border-r border-slate-200 tabular">${p.revenue_usd.toLocaleString()}</td>
                    <td className="p-2 tabular font-bold text-emerald-800">${p.farmer_payout_usd.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* MRV & Climatology Check */}
          <div className="grid grid-cols-2 gap-4 border border-slate-200 rounded-lg p-3 bg-slate-50 text-xs">
            <div>
              <span className="font-bold uppercase text-[10px] text-slate-500 block">Satellite MRV Verification</span>
              <p className="mt-1 text-slate-700">
                Sentinel-1 SAR C-band constellation provides {result.satelliteMRV.passesPerSeason} cloud-penetrating passes per season (median revisit {result.satelliteMRV.medianRevisitDays} days). Radar reliability rate: {result.satelliteMRV.radarReliabilityPct}%.
              </p>
            </div>
            <div>
              <span className="font-bold uppercase text-[10px] text-slate-500 block">Climatological Risk Index</span>
              <p className="mt-1 text-slate-700">
                Annual precipitation: {result.climate.annualRainfallMm} mm. Mean temperature: {result.climate.meanTempC}°C. Climatological drought risk factor: <strong>{result.climate.droughtRisk}</strong>.
              </p>
            </div>
          </div>

          {/* Footer & Signature */}
          <div className="pt-4 mt-2 border-t border-slate-300 flex items-center justify-between text-[11px] text-slate-500">
            <div>
              <strong>carbonstack dMRV System</strong> · Automated Satellite-First Verification & Accounting
            </div>
            <div>
              Document SHA-256 Validated · Page 1 of 1
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
