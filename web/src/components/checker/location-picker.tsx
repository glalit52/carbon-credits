"use client";

import {
  Compass,
  Crosshair,
  Layers,
  MapPin,
  Sparkles,
} from "lucide-react";
import { useState } from "react";

import { BoundaryEditor } from "@/components/map/boundary-editor";
import { Button, Card, CardHeader, Field, Input, Select } from "@/components/ui";
import type { RiceEcosystem, Tenure, WaterControl } from "@/lib/database.types";
import { TENURE_LABEL } from "@/lib/format";

import {
  type CheckInput,
  type MeasurementTier,
  type Pathway,
  POPULAR_PRESETS,
  synthesizeBoundary,
} from "@/lib/checker-engine";

interface LocationPickerProps {
  value: CheckInput;
  onChange: (val: CheckInput) => void;
  onRunCheck: () => void;
  onSave: () => void;
  isSaved?: boolean;
}

export function LocationPicker({ value, onChange, onRunCheck, onSave, isSaved }: LocationPickerProps) {
  const [tab, setTab] = useState<"quick" | "draw">("quick");
  const [unit, setUnit] = useState<"ha" | "acres">("ha");

  const update = (patch: Partial<CheckInput>) => {
    onChange({ ...value, ...patch });
  };

  const applyPreset = (presetId: string) => {
    const p = POPULAR_PRESETS.find((x) => x.id === presetId);
    if (!p) return;
    const boundary = synthesizeBoundary(p.lat, p.lon, p.area_ha);
    onChange({
      ...value,
      name: `${p.title} Field`,
      lat: p.lat,
      lon: p.lon,
      area_ha: p.area_ha,
      boundary,
      pathway: p.pathway,
      crop: p.crop,
      practice: p.practice,
      rice_ecosystem: p.rice_ecosystem,
      water_control: p.water_control,
      seasons_per_year: p.seasons_per_year,
      season_days: p.season_days,
      stems_planted_per_ha: p.stems_planted_per_ha ?? 120,
      tree_species: p.tree_species,
      notes: p.description,
    });
  };

  const locateUser = () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = Number(pos.coords.latitude.toFixed(6));
        const lon = Number(pos.coords.longitude.toFixed(6));
        const boundary = synthesizeBoundary(lat, lon, value.area_ha);
        update({ lat, lon, boundary });
      },
      (err) => console.warn(err.message),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  return (
    <div className="flex flex-col gap-5">
      {/* Popular agricultural preset shortcuts */}
      <Card className="p-4 bg-surface-2/40">
        <div className="flex flex-col gap-2.5">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted">
              <Sparkles className="h-3.5 w-3.5 text-brand" /> Quick Location Presets
            </span>
            <span className="text-xs text-muted">Click to auto-populate coordinates & agricultural params</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {POPULAR_PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => applyPreset(p.id)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-text hover:border-brand hover:bg-brand-soft hover:text-brand-strong transition shadow-xs"
              >
                <MapPin className="h-3 w-3 text-brand" />
                <span>{p.title}</span>
                <span className="text-[10px] text-muted">({p.pathway})</span>
              </button>
            ))}
          </div>
        </div>
      </Card>

      {/* Mode selection: Coordinates vs Map Drawing */}
      <Card>
        <CardHeader
          title="Location & Field Boundary"
          description="Enter GPS coordinates directly or draw/walk the polygon on satellite imagery."
          action={
            <div className="flex rounded-lg bg-surface-2 p-0.5">
              <button
                type="button"
                onClick={() => setTab("quick")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition ${
                  tab === "quick" ? "bg-surface text-text shadow-xs" : "text-muted hover:text-text"
                }`}
              >
                <Compass className="h-3.5 w-3.5" /> Coordinates
              </button>
              <button
                type="button"
                onClick={() => setTab("draw")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition ${
                  tab === "draw" ? "bg-surface text-text shadow-xs" : "text-muted hover:text-text"
                }`}
              >
                <Layers className="h-3.5 w-3.5" /> Map Drawing & Upload
              </button>
            </div>
          }
        />

        <div className="p-5">
          {tab === "quick" ? (
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Latitude" hint="Degrees north/south (-90 to 90)">
                <div className="relative">
                  <Input
                    type="number"
                    step="0.000001"
                    value={value.lat}
                    onChange={(e) => {
                      const lat = Number(e.target.value);
                      update({ lat, boundary: synthesizeBoundary(lat, value.lon, value.area_ha) });
                    }}
                  />
                </div>
              </Field>

              <Field label="Longitude" hint="Degrees east/west (-180 to 180)">
                <Input
                  type="number"
                  step="0.000001"
                  value={value.lon}
                  onChange={(e) => {
                    const lon = Number(e.target.value);
                    update({ lon, boundary: synthesizeBoundary(value.lat, lon, value.area_ha) });
                  }}
                />
              </Field>

              <Field
                label={`Area (${unit === "ha" ? "Hectares" : "Acres"})`}
                hint={
                  <span className="flex items-center justify-between">
                    <span>
                      {unit === "ha"
                        ? `${(value.area_ha * 2.471).toFixed(2)} acres`
                        : `${(value.area_ha).toFixed(2)} ha`}
                    </span>
                    <button
                      type="button"
                      onClick={() => setUnit(unit === "ha" ? "acres" : "ha")}
                      className="text-brand font-medium hover:underline text-[11px]"
                    >
                      switch to {unit === "ha" ? "acres" : "ha"}
                    </button>
                  </span>
                }
              >
                <Input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={unit === "ha" ? value.area_ha : Number((value.area_ha * 2.471).toFixed(2))}
                  onChange={(e) => {
                    const val = Number(e.target.value);
                    const ha = unit === "ha" ? val : val / 2.471;
                    update({ area_ha: ha, boundary: synthesizeBoundary(value.lat, value.lon, ha) });
                  }}
                />
              </Field>

              <div className="sm:col-span-3 flex justify-end">
                <Button type="button" variant="secondary" className="text-xs py-1.5" onClick={locateUser}>
                  <Crosshair className="h-3.5 w-3.5" /> Use my current GPS position
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <BoundaryEditor
                initial={value.boundary ?? synthesizeBoundary(value.lat, value.lon, value.area_ha)}
                center={[value.lon, value.lat]}
              />
              <div className="flex items-center justify-between text-xs text-muted pt-2 border-t border-border">
                <span>
                  Centroid: <strong className="tabular">{value.lat.toFixed(5)}, {value.lon.toFixed(5)}</strong>
                </span>
                <span>
                  Area: <strong className="tabular">{value.area_ha.toFixed(2)} ha</strong> ({(value.area_ha * 2.471).toFixed(2)} acres)
                </span>
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* Field Identification & Practice Configuration */}
      <Card>
        <CardHeader title="Agricultural Parameters & Practice" description="Define the intervention and methodology configuration." />
        <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Field / Location Name" className="sm:col-span-2">
            <Input
              value={value.name}
              onChange={(e) => update({ name: e.target.value })}
              placeholder="e.g. Kaveri Basin North Plot or Gatugi Block 4"
            />
          </Field>

          <Field label="Farmer / Landowner (Optional)">
            <Input
              value={value.farmer_name ?? ""}
              onChange={(e) => update({ farmer_name: e.target.value })}
              placeholder="e.g. S. Ramanathan"
            />
          </Field>

          <Field label="Pathway">
            <Select
              value={value.pathway}
              onChange={(e) => {
                const pathway = e.target.value as Pathway;
                update({
                  pathway,
                  practice: pathway === "rice" ? "awd" : pathway === "agroforestry" ? "shade_trees" : "cover_crops_biochar",
                  crop: pathway === "rice" ? "Paddy Rice" : pathway === "agroforestry" ? "Coffee under Shade" : "Legume cover crop",
                });
              }}
            >
              <option value="rice">Rice Cultivation (VM0051 Methane Avoidance)</option>
              <option value="agroforestry">Agroforestry & Trees (VM0047 Carbon Removal)</option>
              <option value="soil">Regenerative Soil / ALM (VM0042 Soil Carbon)</option>
            </Select>
          </Field>

          <Field label="Crop Variety / Cultivar">
            <Input value={value.crop ?? ""} onChange={(e) => update({ crop: e.target.value })} placeholder="e.g. CR 1009 / Basmati / Arabica" />
          </Field>

          <Field label="Practice / Intervention">
            {value.pathway === "rice" ? (
              <Select value={value.practice} onChange={(e) => update({ practice: e.target.value })}>
                <option value="awd">Alternate Wetting & Drying (AWD - Multiple Drainage)</option>
                <option value="single_drainage">Single Mid-Season Drainage</option>
                <option value="continuous_flood">Continuous Flooding (Baseline - Zero credits)</option>
              </Select>
            ) : value.pathway === "agroforestry" ? (
              <Select value={value.practice} onChange={(e) => update({ practice: e.target.value })}>
                <option value="shade_trees">Shade Canopy Trees in Crops (Coffee/Cocoa/Tea)</option>
                <option value="timber_trees">Boundary & Woodlot Timber Planting</option>
                <option value="fruit_orchard">Orchard & Agro-silviculture</option>
              </Select>
            ) : (
              <Select value={value.practice} onChange={(e) => update({ practice: e.target.value })}>
                <option value="cover_crops_biochar">Cover Cropping + Biochar Amendment</option>
                <option value="reduced_tillage">No-Till / Reduced Tillage System</option>
                <option value="compost_mulch">Organic Composting & Mulch Retention</option>
              </Select>
            )}
          </Field>

          {/* Conditional parameters for Rice */}
          {value.pathway === "rice" && (
            <>
              <Field label="Rice Ecosystem" hint="VM0051 credits irrigated lowland only">
                <Select
                  value={value.rice_ecosystem ?? "irrigated_lowland"}
                  onChange={(e) => update({ rice_ecosystem: e.target.value as RiceEcosystem })}
                >
                  <option value="irrigated_lowland">Irrigated Lowland (Eligible)</option>
                  <option value="rainfed">Rainfed (Ineligible for VM0051)</option>
                  <option value="upland">Upland (Ineligible for VM0051)</option>
                  <option value="deepwater">Deepwater (Ineligible for VM0051)</option>
                </Select>
              </Field>

              <Field label="Water Control Infrastructure" hint="AWD requires drainage gate/outflow">
                <Select
                  value={value.water_control ?? "full"}
                  onChange={(e) => update({ water_control: e.target.value as WaterControl })}
                >
                  <option value="full">Full Irrigation & Drainage Control</option>
                  <option value="irrigation_only">Irrigation Only (Restricted Drainage)</option>
                  <option value="none">No Controlled Gates (Ineligible)</option>
                </Select>
              </Field>

              <Field label="Seasons Per Year">
                <Select
                  value={value.seasons_per_year ?? 2}
                  onChange={(e) => update({ seasons_per_year: Number(e.target.value) })}
                >
                  <option value={1}>1 Season / Year</option>
                  <option value={2}>2 Seasons / Year (e.g. Kharif + Rabi)</option>
                  <option value={3}>3 Seasons / Year (Intensive Tri-crop)</option>
                </Select>
              </Field>
            </>
          )}

          {/* Conditional parameters for Agroforestry */}
          {value.pathway === "agroforestry" && (
            <>
              <Field label="Tree Species" hint="Comma-separated species">
                <Input
                  value={value.tree_species ?? ""}
                  onChange={(e) => update({ tree_species: e.target.value })}
                  placeholder="e.g. Grevillea robusta, Cordia africana"
                />
              </Field>

              <Field label="Tree Density (Stems / ha)" hint="Average stand density">
                <Input
                  type="number"
                  min="10"
                  max="2500"
                  value={value.stems_planted_per_ha ?? 120}
                  onChange={(e) => update({ stems_planted_per_ha: Number(e.target.value) })}
                />
              </Field>
            </>
          )}

          {/* Tenure & Eligibility Documentation */}
          <Field label="Land Tenure Basis" hint="Documentation proves ownership/consent">
            <Select value={value.tenure} onChange={(e) => update({ tenure: e.target.value as Tenure })}>
              {Object.entries(TENURE_LABEL).map(([val, label]) => (
                <option key={val} value={val}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Tenure Document Reference" hint="Patta, Title deed, or lease no.">
            <Input
              value={value.tenure_reference ?? ""}
              onChange={(e) => update({ tenure_reference: e.target.value })}
              placeholder="e.g. PATTA-2024-4902"
            />
          </Field>

          <Field label="Measurement Tier" hint="Asset precision affects uncertainty deduction">
            <Select
              value={value.measurement_tier ?? 1}
              onChange={(e) => update({ measurement_tier: Number(e.target.value) as MeasurementTier })}
            >
              <option value={1}>Tier 1: IPCC Generic Default (35% deduction penalty)</option>
              <option value={2}>Tier 2: National Country Inventory (15% deduction penalty)</option>
              <option value={3}>Tier 3: Calibrated Flux Tower / Allometry (0% penalty)</option>
            </Select>
          </Field>
        </div>
      </Card>

      {/* Commercial & Financial Assumptions */}
      <Card>
        <CardHeader title="Commercial Terms & Financial Assumptions" description="Pricing and revenue split assumptions." />
        <div className="grid gap-4 p-5 sm:grid-cols-3">
          <Field label="Carbon Price ($/tCO2e)" hint="Market buyer rate per credit">
            <div className="relative">
              <span className="absolute left-3 top-2 text-muted text-sm">$</span>
              <Input
                type="number"
                step="0.5"
                min="1"
                className="pl-7"
                value={value.carbon_price_usd ?? 15}
                onChange={(e) => update({ carbon_price_usd: Number(e.target.value) })}
              />
            </div>
          </Field>

          <Field label="Farmer Revenue Share (%)" hint="Fair share percentage paid to farmer">
            <div className="relative">
              <Input
                type="number"
                step="1"
                min="10"
                max="90"
                value={value.farmer_share_pct ?? 60}
                onChange={(e) => update({ farmer_share_pct: Number(e.target.value) })}
              />
              <span className="absolute right-3 top-2 text-muted text-sm">%</span>
            </div>
          </Field>

          <Field label="Marginal MRV Cost ($/ha/yr)" hint="Satellite & verification cost">
            <div className="relative">
              <span className="absolute left-3 top-2 text-muted text-sm">$</span>
              <Input
                type="number"
                step="0.1"
                min="0.5"
                className="pl-7"
                value={value.monitoring_cost_per_ha ?? 6.2}
                onChange={(e) => update({ monitoring_cost_per_ha: Number(e.target.value) })}
              />
            </div>
          </Field>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-3.5 bg-surface-2/20">
          <div className="text-xs text-muted">
            All formulas strictly adhere to Verra VM0051 / VM0047 and IPCC 2019 Refinements.
          </div>
          <div className="flex items-center gap-2">
            <Button type="button" variant="secondary" onClick={onSave}>
              {isSaved ? "Update Saved Field" : "Save this Location"}
            </Button>
            <Button type="button" onClick={onRunCheck} className="px-5">
              Run Feasibility & MRV Check
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
