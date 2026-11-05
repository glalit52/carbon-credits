"use client";

import { Globe, Map, Scale } from "lucide-react";
import { useState } from "react";

import { ProfileNav } from "@/components/profile/profile-nav";
import { Button, Card, CardHeader, Field, Notice, PageHeader, Select } from "@/components/ui";

const PREF_KEY = "carbonstack_user_preferences_v1";

interface UserPreferences {
  areaUnit: "ha" | "acres";
  distanceUnit: "metric" | "imperial";
  currency: "USD" | "EUR" | "INR" | "KES";
  defaultMethodology: "VM0051" | "VM0047" | "VM0042";
  mapBase: "satellite" | "streets";
  dateFormat: "YYYY-MM-DD" | "DD/MM/YYYY" | "MM/DD/YYYY";
  autoRefreshCadence: "5s" | "15s" | "manual";
  highContrastMRV: boolean;
}

const DEFAULT_PREFS: UserPreferences = {
  areaUnit: "ha",
  distanceUnit: "metric",
  currency: "USD",
  defaultMethodology: "VM0051",
  mapBase: "satellite",
  dateFormat: "YYYY-MM-DD",
  autoRefreshCadence: "15s",
  highContrastMRV: true,
};

export default function PreferencesPage() {
  const [prefs, setPrefs] = useState<UserPreferences>(() => {
    if (typeof window === "undefined") return DEFAULT_PREFS;
    try {
      const saved = localStorage.getItem(PREF_KEY);
      return saved ? JSON.parse(saved) : DEFAULT_PREFS;
    } catch {
      return DEFAULT_PREFS;
    }
  });

  const [savedMessage, setSavedMessage] = useState(false);

  const handleSave = () => {
    localStorage.setItem(PREF_KEY, JSON.stringify(prefs));
    setSavedMessage(true);
    setTimeout(() => setSavedMessage(false), 3000);
  };

  return (
    <>
      <PageHeader
        title="Preferences & Agronomic Units"
        crumbs={[{ href: "/app/profile", label: "Profile" }, { href: "/app/profile/preferences", label: "Preferences" }]}
        description="Configure unit conventions, financial currencies, and mapping styles for your workspace."
      />
      <ProfileNav />

      {savedMessage && (
        <div className="mb-6">
          <Notice tone="brand">✓ Preferences saved successfully.</Notice>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Measurement & Units */}
        <Card>
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <Scale className="h-4 w-4 text-brand" />
                <span>Measurement & Agronomic Units</span>
              </div>
            }
            description="Units used for plot areas, radar backscatter, and biomass."
          />
          <div className="p-5 flex flex-col gap-4">
            <Field label="Land Area Unit" hint="Displayed across maps, forms, and estimate summaries">
              <Select
                value={prefs.areaUnit}
                onChange={(e) => setPrefs({ ...prefs, areaUnit: e.target.value as "ha" | "acres" })}
              >
                <option value="ha">Metric Hectares (ha) - Standard (1 ha = 10,000 m²)</option>
                <option value="acres">Imperial Acres (ac) - (1 ha ≈ 2.471 acres)</option>
              </Select>
            </Field>

            <Field label="Distance & Tree Height" hint="Tree canopy heights and water-level sensor depth">
              <Select
                value={prefs.distanceUnit}
                onChange={(e) => setPrefs({ ...prefs, distanceUnit: e.target.value as "metric" | "imperial" })}
              >
                <option value="metric">Metric (Meters / Centimeters)</option>
                <option value="imperial">Imperial (Feet / Inches)</option>
              </Select>
            </Field>

            <Field label="Default Quantification Methodology" hint="Pre-selected methodology for new candidate plots">
              <Select
                value={prefs.defaultMethodology}
                onChange={(e) => setPrefs({ ...prefs, defaultMethodology: e.target.value as "VM0051" | "VM0047" | "VM0042" })}
              >
                <option value="VM0051">VM0051 - Rice Production & Avoided Methane (CORSIA Eligible)</option>
                <option value="VM0047">VM0047 - Afforestation, Reforestation & Revegetation (ARR)</option>
                <option value="VM0042">VM0042 - Improved Agricultural Land Management (Soil Carbon)</option>
              </Select>
            </Field>
          </div>
        </Card>

        {/* Currency & Regional Locale */}
        <Card>
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <Globe className="h-4 w-4 text-brand" />
                <span>Financial Currency & Locale</span>
              </div>
            }
            description="Currencies for farmer benefit-sharing payouts and credit sales."
          />
          <div className="p-5 flex flex-col gap-4">
            <Field label="Primary Reporting Currency" hint="Carbon price and farmer settlement currency">
              <Select
                value={prefs.currency}
                onChange={(e) => setPrefs({ ...prefs, currency: e.target.value as "USD" | "EUR" | "INR" | "KES" })}
              >
                <option value="USD">USD ($) - United States Dollar (Global Carbon Benchmark)</option>
                <option value="EUR">EUR (€) - Euro</option>
                <option value="INR">INR (₹) - Indian Rupee (Thanjavur & Punjab Pilots)</option>
                <option value="KES">KES (KSh) - Kenyan Shilling (Nyeri Pilot)</option>
              </Select>
            </Field>

            <Field label="Date & Calendar Format" hint="For crop sowing and verification cycles">
              <Select
                value={prefs.dateFormat}
                onChange={(e) => setPrefs({ ...prefs, dateFormat: e.target.value as "YYYY-MM-DD" | "DD/MM/YYYY" | "MM/DD/YYYY" })}
              >
                <option value="YYYY-MM-DD">ISO 8601 (YYYY-MM-DD) - Standard</option>
                <option value="DD/MM/YYYY">DD/MM/YYYY - British / Indian Commonwealth</option>
                <option value="MM/DD/YYYY">MM/DD/YYYY - US Standard</option>
              </Select>
            </Field>
          </div>
        </Card>

        {/* Map & MRV Visualization */}
        <Card className="lg:col-span-2">
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <Map className="h-4 w-4 text-brand" />
                <span>Map & Satellite Imagery Display</span>
              </div>
            }
            description="Display options for field maps, satellite passes, and boundary editors."
          />
          <div className="p-5 grid gap-4 sm:grid-cols-2">
            <Field label="Default Map Layer">
              <Select
                value={prefs.mapBase}
                onChange={(e) => setPrefs({ ...prefs, mapBase: e.target.value as "satellite" | "streets" })}
              >
                <option value="satellite">High-Resolution Satellite Imagery</option>
                <option value="streets">Topographic Street & Terrain Vector</option>
              </Select>
            </Field>

            <Field label="Telemetry Polling Interval" hint="Live sensor and radar status update frequency">
              <Select
                value={prefs.autoRefreshCadence}
                onChange={(e) => setPrefs({ ...prefs, autoRefreshCadence: e.target.value as "5s" | "15s" | "manual" })}
              >
                <option value="5s">Every 5 seconds (Real-time)</option>
                <option value="15s">Every 15 seconds (Standard)</option>
                <option value="manual">Manual refresh only</option>
              </Select>
            </Field>

            <div className="sm:col-span-2 flex items-center justify-between p-3 rounded-lg border border-border bg-surface-2/40">
              <div>
                <strong className="text-sm block">High-Contrast Radar Water State Mode</strong>
                <span className="text-xs text-muted">
                  Enhances Sentinel-1 C-band backscatter colors (distinct green for drained AWD dry-downs, blue for flooding).
                </span>
              </div>
              <input
                type="checkbox"
                checked={prefs.highContrastMRV}
                onChange={(e) => setPrefs({ ...prefs, highContrastMRV: e.target.checked })}
                className="h-4 w-4 rounded accent-brand"
              />
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-border px-5 py-3.5 bg-surface-2/20">
            <span className="text-xs text-muted">Preferences are persisted to your browser session.</span>
            <Button type="button" onClick={handleSave}>
              Save Preferences
            </Button>
          </div>
        </Card>
      </div>
    </>
  );
}
